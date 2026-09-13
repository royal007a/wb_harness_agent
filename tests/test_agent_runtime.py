import asyncio
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from jsonschema import Draft202012Validator
import yaml

from backend.agent_runtime import AgentRuntime, CONTRACT
from backend.app import create_app
from backend.store import Store


def headers(key):
    return {'Idempotency-Key': key}


@pytest.fixture
def app(tmp_path):
    return create_app(tmp_path / 'agent-runtime.db', run_worker=False)


@pytest.fixture
def client(app):
    with TestClient(app, base_url='http://127.0.0.1') as value:
        yield value


def create_stack(client, credential_ref=None, turns=2):
    provider_body = {'name': '受控 Provider', 'type': 'openai_compatible', 'base_url': 'https://example.invalid'}
    if credential_ref:
        provider_body['credential_ref'] = credential_ref
    provider = client.post('/api/local/agent-runtime/providers', headers=headers('runtime-provider'), json=provider_body)
    assert provider.status_code == 201, provider.text
    model = client.post('/api/local/agent-runtime/models', headers=headers('runtime-model'), json={
        'provider_profile_id': provider.json()['id'], 'display_name': '受控模型', 'model_id': 'controlled-v1', 'context_window': 32768,
    })
    assert model.status_code == 201, model.text
    agent = client.post('/api/local/agent-runtime/agents', headers=headers('runtime-agent'), json={
        'name': '研究 Agent', 'description': '只验证隔离运行时。', 'system_prompt': '基于来源回答。',
        'model_profile_id': model.json()['id'], 'temperature': 0.2, 'max_output_tokens': 512, 'max_context_turns': turns,
    })
    assert agent.status_code == 201, agent.text
    return provider.json(), model.json(), agent.json()


def event_list(response):
    return [json.loads(line[6:]) for line in ''.join(response.iter_text()).splitlines() if line.startswith('data: ')]


def test_runtime_contract_and_default_gate_are_truthful(client, app):
    forbidden = client.post('/api/local/agent-runtime/providers', headers=headers('bad-secret'), json={
        'name': '坏配置', 'type': 'openai_compatible', 'base_url': 'https://example.invalid', 'api_key': 'do-not-store',
    })
    assert forbidden.status_code == 422
    malformed_ref = client.post('/api/local/agent-runtime/providers', headers=headers('bad-ref'), json={
        'name': '坏引用', 'type': 'openai_compatible', 'base_url': 'https://example.invalid', 'credential_ref': 'sk-secret-value',
    })
    assert malformed_ref.status_code == 422
    provider, model, agent = create_stack(client)
    for definition, value in [('provider_profile', provider), ('model_profile', model), ('agent_profile', agent)]:
        schema = {'$ref': '#/$defs/' + definition, '$defs': CONTRACT['$defs']}
        assert Draft202012Validator(schema).is_valid(value)
    readiness = client.get(f"/api/local/agent-runtime/providers/{provider['id']}/readiness").json()
    assert readiness['state'] == 'blocked_by_runtime_gate'
    assert readiness['network_calls'] == 0
    session = client.post('/api/local/agent-runtime/sessions', headers=headers('runtime-session'), json={'agent_profile_id': agent['id']})
    assert session.status_code == 201
    endpoint = f"/api/local/agent-runtime/sessions/{session.json()['id']}/messages"
    with client.stream('POST', endpoint, headers={**headers('runtime-message'), 'Accept': 'text/event-stream'}, json={'content': '请给出系统设计。'}) as response:
        assert response.status_code == 200
        events = event_list(response)
    assert events == [{'type': 'error', 'exchange_id': events[0]['exchange_id'], 'error_code': 'MODEL_RUNTIME_DISABLED', 'model_calls': 0, 'provider_calls': 0}]
    detail = client.get(f"/api/local/agent-runtime/sessions/{session.json()['id']}").json()
    assert [message['role'] for message in detail['messages']] == ['user']
    assert detail['exchanges'][0]['status'] == 'failed'
    assert detail['exchanges'][0]['assistant_message_id'] is None
    assert len(app.state.service.store.listing('tasks')) == len(app.state.service.store.listing('runs')) == 0


class CapturingAdapter:
    adapter_status = 'supported'

    def __init__(self):
        self.requests = []

    async def stream(self, request):
        self.requests.append(request)
        yield '已收到。'


class CapturingRegistry:
    def __init__(self, adapter):
        self.adapter = adapter

    def status_for(self, provider_type):
        return 'supported' if provider_type == 'openai_compatible' else 'not_implemented'

    def require(self, provider_type):
        assert provider_type == 'openai_compatible'
        return self.adapter


class FixedResolver:
    def resolve(self, credential_ref):
        assert credential_ref == 'keychain://harnessagent/test-provider'
        return 'not-persisted-test-token'


async def collect(iterator):
    return [item async for item in iterator]


def test_enabled_runtime_uses_bounded_context_and_persists_only_real_adapter_output(tmp_path):
    store = Store(tmp_path / 'runtime-isolated.db')
    adapter = CapturingAdapter()
    runtime = AgentRuntime(store, adapter_registry=CapturingRegistry(adapter), credential_resolver=FixedResolver(), runtime_enabled=True)
    try:
        provider = runtime.create_provider({'name': '测试 Provider', 'type': 'openai_compatible', 'base_url': 'https://example.invalid', 'credential_ref': 'keychain://harnessagent/test-provider'}, 'one')
        model = runtime.create_model({'provider_profile_id': provider['id'], 'display_name': '测试模型', 'model_id': 'model-v1', 'context_window': 4096}, 'two')
        agent = runtime.create_agent({'name': '测试 Agent', 'description': '', 'system_prompt': '系统约束。', 'model_profile_id': model['id'], 'temperature': 0.1, 'max_output_tokens': 128, 'max_context_turns': 1}, 'three')
        session = runtime.create_session({'agent_profile_id': agent['id']}, 'four')
        for number in range(3):
            exchange = runtime.prepare_exchange(session['id'], {'content': f'问题 {number}'}, f'message-{number}')
            events = asyncio.run(collect(runtime.stream_exchange(exchange['id'])))
            assert events[-1]['type'] == 'done'
        assert len(adapter.requests) == 3
        last = adapter.requests[-1]
        assert last.system_prompt == '系统约束。'
        assert last.messages == ({'role': 'assistant', 'content': '已收到。'}, {'role': 'user', 'content': '问题 2'})
        detail_messages = store.runtime_messages(session['id'])
        assert [message['role'] for message in detail_messages] == ['user', 'assistant'] * 3
        exchange = store.runtime_exchanges(session['id'])[-1]
        assert exchange['status'] == 'succeeded'
        assert exchange['model_calls'] == exchange['provider_calls'] == 1
        assert 'not-persisted-test-token' not in json.dumps(detail_messages, ensure_ascii=False)
    finally:
        store.close()


def test_runtime_openapi_declares_separate_stream_contract(client):
    openapi = client.get('/openapi.json').json()
    operation = openapi['paths']['/api/local/agent-runtime/sessions/{session_id}/messages']['post']
    assert operation['requestBody']['content']['application/json']['schema'] == {
        '$ref': '#/components/schemas/send_message_request'}
    assert operation['responses']['200']['content']['text/event-stream']['schema'] == {
        '$ref': '#/components/schemas/runtime_stream_event'}
    static = yaml.safe_load((Path(__file__).resolve().parents[1] / 'specs/v1/openapi.yaml').read_text())
    endpoint = static['paths']['/local/agent-runtime/sessions/{sessionId}/messages']['post']
    assert endpoint['requestBody']['content']['application/json']['schema']['$ref'].endswith('#/$defs/send_message_request')
    assert endpoint['responses']['200']['content']['text/event-stream']['schema']['$ref'].endswith('#/$defs/runtime_stream_event')
