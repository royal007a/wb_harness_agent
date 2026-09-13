import json

import pytest
from fastapi.testclient import TestClient
from jsonschema import Draft202012Validator
import yaml

from backend.agent_lab import CONTRACT
from backend.app import create_app
from backend.service import ROOT


@pytest.fixture
def app(tmp_path):
    return create_app(tmp_path / 'agent-lab.db', run_worker=False)


@pytest.fixture
def client(app):
    with TestClient(app, base_url='http://127.0.0.1') as value:
        yield value


def headers(key):
    return {'Idempotency-Key': key}


def create_profiles(client):
    provider = client.post('/api/local/agent-lab/providers', headers=headers('provider-one'), json={
        'name': '受控测试 Provider', 'type': 'openai_compatible', 'base_url': 'https://example.invalid',
    })
    assert provider.status_code == 201, provider.text
    model = client.post('/api/local/agent-lab/models', headers=headers('model-one'), json={
        'provider_profile_id': provider.json()['id'], 'display_name': '测试模型', 'model_id': 'test-model-v1',
        'context_window': 32768,
    })
    assert model.status_code == 201, model.text
    agent = client.post('/api/local/agent-lab/agents', headers=headers('agent-one'), json={
        'name': '测试 Agent', 'description': '只验证本地流式链路。',
        'system_prompt': '你是一个本地演示配置，不得宣称调用了真实模型。',
        'model_profile_id': model.json()['id'], 'temperature': 0.3,
        'max_output_tokens': 1024, 'max_context_turns': 8,
    })
    assert agent.status_code == 201, agent.text
    return provider.json(), model.json(), agent.json()


def test_agent_lab_contracts_are_strict_and_credential_free(client):
    response = client.post('/api/local/agent-lab/providers', headers=headers('unknown-field'), json={
        'name': '错误配置', 'type': 'openai_compatible', 'base_url': 'https://example.invalid', 'credential_ref': 'secret://key',
    })
    assert response.status_code == 422
    sensitive = client.post('/api/local/agent-lab/providers', headers=headers('sensitive-field'), json={
        'name': 'api_key=should-not-be-stored', 'type': 'openai_compatible', 'base_url': 'https://example.invalid',
    })
    assert sensitive.status_code == 422
    insecure = client.post('/api/local/agent-lab/providers', headers=headers('insecure-url'), json={
        'name': '外部 HTTP', 'type': 'openai_compatible', 'base_url': 'http://provider.invalid',
    })
    assert insecure.status_code == 422
    disabled = client.post('/api/local/agent-lab/providers', headers=headers('disabled-provider'), json={
        'name': '禁用 Provider', 'type': 'ollama', 'base_url': 'http://localhost:11434', 'enabled': False,
    })
    assert disabled.status_code == 201
    child = client.post('/api/local/agent-lab/models', headers=headers('disabled-model'), json={
        'provider_profile_id': disabled.json()['id'], 'display_name': '不能创建', 'model_id': 'local', 'context_window': 4096,
    })
    assert child.status_code == 409
    provider, model, agent = create_profiles(client)
    for definition, value in [('provider_profile', provider), ('model_profile', model), ('agent_profile', agent)]:
        schema = {'$ref': '#/$defs/' + definition, '$defs': CONTRACT['$defs']}
        assert Draft202012Validator(schema).is_valid(value)
    assert agent['tool_binding_count'] == 0
    assert client.get('/api/local/agent-lab/runtime').json() == {
        'mode': 'local_deterministic_demo', 'model_calls': 0, 'provider_calls': 0, 'network_calls': 0,
        'tool_calls': 0, 'tool_binding_count': 0, 'note': '仅验证配置、会话和流式交互；真实模型未启用。',
    }


def test_agent_lab_session_stream_is_persistent_idempotent_and_zero_model(client, app):
    _provider, _model, agent = create_profiles(client)
    session = client.post('/api/local/agent-lab/sessions', headers=headers('session-one'), json={
        'agent_profile_id': agent['id'],
    })
    assert session.status_code == 201
    session_id = session.json()['id']
    endpoint = f'/api/local/agent-lab/sessions/{session_id}/messages'
    key = 'message-one'
    with client.stream('POST', endpoint, headers={**headers(key), 'Accept': 'text/event-stream'}, json={'content': '请验证 SSE。'}) as response:
        body = ''.join(response.iter_text())
        assert response.status_code == 200
        assert response.headers['content-type'].startswith('text/event-stream')
    events = [json.loads(line[6:]) for line in body.splitlines() if line.startswith('data: ')]
    assert [event['type'] for event in events] == ['delta', 'delta', 'delta', 'delta', 'done']
    assert events[-1] == {
        'type': 'done', 'message_id': events[0]['message_id'], 'finish_reason': 'stop',
        'model_calls': 0, 'provider_calls': 0,
    }
    assert all(event['model_calls'] == event['provider_calls'] == 0 for event in events)
    detail = client.get(f'/api/local/agent-lab/sessions/{session_id}').json()
    assert [message['role'] for message in detail['messages']] == ['user', 'assistant']
    assert detail['messages'][1]['generation'] == 'local_demo'
    assert '不是模型对问题的实际回答' in detail['messages'][1]['content']
    stored_before = app.state.service.store.chat_messages(session_id)
    with client.stream('POST', endpoint, headers={**headers(key), 'Accept': 'text/event-stream'}, json={'content': '请验证 SSE。'}) as replay:
        assert replay.status_code == 200
        assert '"type": "done"' in ''.join(replay.iter_text())
    assert app.state.service.store.chat_messages(session_id) == stored_before
    conflict = client.post(endpoint, headers={**headers(key), 'Accept': 'text/event-stream'}, json={'content': '不同内容'})
    assert conflict.status_code == 409
    missing_accept = client.post(endpoint, headers=headers('message-without-accept'), json={'content': '不会发送'})
    assert missing_accept.status_code == 406
    assert len(app.state.service.store.listing('tasks')) == len(app.state.service.store.listing('runs')) == 0


def test_agent_lab_session_and_message_contracts_are_valid(client):
    _provider, _model, agent = create_profiles(client)
    session = client.post('/api/local/agent-lab/sessions', headers=headers('session-schema'), json={
        'agent_profile_id': agent['id'], 'title': '本地验证',
    }).json()
    with client.stream('POST', f"/api/local/agent-lab/sessions/{session['id']}/messages", headers={**headers('message-schema'), 'Accept': 'text/event-stream'}, json={'content': '验证契约'}) as response:
        assert response.status_code == 200
        list(response.iter_text())
    detail = client.get(f"/api/local/agent-lab/sessions/{session['id']}").json()
    for definition, value in [('chat_session', detail['session'])] + [('chat_message', item) for item in detail['messages']]:
        schema = {'$ref': '#/$defs/' + definition, '$defs': CONTRACT['$defs']}
        assert Draft202012Validator(schema).is_valid(value)
    openapi = client.get('/openapi.json').json()
    operation = openapi['paths']['/api/local/agent-lab/sessions/{session_id}/messages']['post']
    assert operation['requestBody']['content']['application/json']['schema'] == {
        '$ref': '#/components/schemas/send_message_request'}
    assert 'text/event-stream' in operation['responses']['200']['content']
    static = yaml.safe_load((ROOT / 'specs/v1/openapi.yaml').read_text())
    static_path = static['paths']['/local/agent-lab/sessions/{sessionId}/messages']
    static_operation = static_path['post']
    assert static_path['servers'] == [{'url': '/api'}]
    assert static_operation['requestBody']['content']['application/json']['schema']['$ref'].endswith('#/$defs/send_message_request')
    assert 'text/event-stream' in static_operation['responses']['200']['content']
