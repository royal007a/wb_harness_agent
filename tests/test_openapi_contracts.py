"""Published OpenAPI must validate actual local HTTP instances, without external I/O."""
import copy
import json
from pathlib import Path

import pytest
import yaml
from fastapi.testclient import TestClient
from jsonschema import Draft202012Validator, FormatChecker

from backend.app import create_app
from backend.research_agents import agent_registry

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.delenv('HARNESS_AGENT_RUNTIME', raising=False)
    with TestClient(create_app(tmp_path / 'contract.db', run_worker=False), base_url='http://127.0.0.1') as value:
        def forbidden(*args, **kwargs):
            pytest.fail('OpenAPI tests may not resolve credentials or request a Provider')
        value.app.state.service.agent_runtime.credentials.resolve = forbidden
        value.app.state.service.agent_runtime.adapters.require = forbidden
        yield value


def validator(document, schema):
    assert schema, 'Published response must not be an unconstrained placeholder'
    return Draft202012Validator({**document, **schema}, format_checker=FormatChecker())


def request_validator(client, domain, resource):
    document = client.get('/openapi.json').json()
    operation = document['paths'][f'/api/local/{domain}/{resource}']['post']
    return validator(document, operation['requestBody']['content']['application/json']['schema'])


def make_stack(client, domain):
    profiles, requests = {}, {}
    for resource in ('providers', 'models', 'agents', 'sessions'):
        body = {
            'providers': {'name': 'Fixture', 'type': 'openai_compatible', 'base_url': 'https://example.invalid'},
            'models': {'provider_profile_id': profiles.get('providers', {}).get('id'),
                       'display_name': 'Fixture', 'model_id': 'test', 'context_window': 4096},
            'agents': {'name': 'Fixture', 'description': '', 'system_prompt': 'Fixture prompt',
                       'model_profile_id': profiles.get('models', {}).get('id'), 'temperature': 0,
                       'max_output_tokens': 128, 'max_context_turns': 2},
            'sessions': {'agent_profile_id': profiles.get('agents', {}).get('id'), 'title': 'Fixture'},
        }[resource]
        response = client.post(f'/api/local/{domain}/{resource}', json=body,
                               headers={'Idempotency-Key': domain + '-' + resource})
        assert response.status_code == 201, response.text
        profiles[resource], requests[resource] = response.json(), body
    return profiles, requests


@pytest.mark.parametrize('resource', ['models', 'agents', 'sessions'])
def test_lab_published_request_accepts_its_actual_ids(client, resource):
    _, requests = make_stack(client, 'agent-lab')
    request_validator(client, 'agent-lab', resource).validate(requests[resource])


def test_lab_published_request_rejects_runtime_credential_field(client):
    body = {'name': 'Fixture', 'type': 'openai_compatible', 'base_url': 'https://example.invalid',
            'credential_ref': 'keychain://harnessagent/test'}
    response = client.post('/api/local/agent-lab/providers', json=body, headers={'Idempotency-Key': 'no-credential'})
    assert response.status_code == 422
    assert not request_validator(client, 'agent-lab', 'providers').is_valid(body)
    request_validator(client, 'agent-runtime', 'providers').validate(body)


def test_research_definition_keeps_its_own_nested_skill_contract(client):
    document = client.get('/openapi.json').json()
    ref = document['paths']['/api/local/research-agents']['post']['requestBody']['content']['application/json']['schema']['$ref']
    agent_ref = ref.removesuffix('research_agent_request') + 'agent_definition'
    for agent in agent_registry():
        validator(document, {'$ref': agent_ref}).validate(agent)


@pytest.mark.parametrize('domain', ['agent-lab', 'agent-runtime'])
def test_profile_creation_response_has_a_real_published_contract(client, domain):
    profiles, _ = make_stack(client, domain)
    other = 'agent-runtime' if domain == 'agent-lab' else 'agent-lab'
    foreign, _ = make_stack(client, other)
    document = client.get('/openapi.json').json()
    for resource, profile in profiles.items():
        schema = document['paths'][f'/api/local/{domain}/{resource}']['post']['responses']['201']['content']['application/json']['schema']
        check = validator(document, schema)
        check.validate(profile)
        assert not check.is_valid({**profile, 'unexpected': True})
        assert not check.is_valid(foreign[resource])


def paired_validators(client, path, method, status=None, media='application/json'):
    dynamic = client.get('/openapi.json').json()
    operation = dynamic['paths'][path][method]
    branch = operation['requestBody'] if status is None else operation['responses'][str(status)]
    dynamic_check = validator(dynamic, branch['content'][media]['schema'])
    static = yaml.safe_load((ROOT / 'specs/v1/openapi.yaml').read_text())
    static_path = path.removeprefix('/api').replace('{session_id}', '{sessionId}').replace('{provider_id}', '{providerId}')
    assert static['paths'][static_path]['servers'] == [{'url': '/api'}]
    operation = static['paths'][static_path][method]
    branch = operation['requestBody'] if status is None else operation['responses'][str(status)]
    schema_ref = branch['content'][media]['schema']['$ref']
    filename, pointer = schema_ref.split('#')
    assert filename in ('./local-agent-lab.schema.json', './agent-runtime.schema.json')
    source = json.loads((ROOT / 'specs/v1' / filename).read_text())
    return dynamic_check, validator(source, {'$ref': '#' + pointer})


def validate_pair(checks, value):
    for check in checks:
        check.validate(value)
        if isinstance(value, dict):
            assert not check.is_valid({**value, 'unknown_field': True})


@pytest.mark.parametrize('domain', ['agent-lab', 'agent-runtime'])
def test_full_chat_http_contract_roundtrip(client, domain):
    prefix = '/api/local/' + domain
    for resource in ('providers', 'models', 'agents', 'sessions'):
        response = client.get(prefix + '/' + resource)
        assert response.status_code == 200 and response.json()['items'] == []
        validate_pair(paired_validators(client, prefix + '/' + resource, 'get', 200), response.json())
    profiles, requests = make_stack(client, domain)
    for resource, profile in profiles.items():
        path = prefix + '/' + resource
        validate_pair(paired_validators(client, path, 'post'), requests[resource])
        validate_pair(paired_validators(client, path, 'post', 201), profile)
        response = client.get(path)
        assert response.status_code == 200 and response.json()['items'] == [profile]
        validate_pair(paired_validators(client, path, 'get', 200), response.json())
        replay = client.post(path, json=requests[resource], headers={'Idempotency-Key': domain + '-' + resource})
        assert replay.status_code == 201 and replay.json() == profile
    status = client.get(prefix + '/runtime')
    assert status.status_code == 200
    validate_pair(paired_validators(client, prefix + '/runtime', 'get', 200), status.json())
    assert status.json()['model_calls'] == status.json()['network_calls'] == 0
    session_path = prefix + '/sessions/' + profiles['sessions']['id']
    detail_contract = paired_validators(client, prefix + '/sessions/{session_id}', 'get', 200)
    before = client.get(session_path)
    assert before.status_code == 200 and before.json()['messages'] == []
    validate_pair(detail_contract, before.json())
    body = {'content': 'Validate local contract'}
    message_path = prefix + '/sessions/{session_id}/messages'
    validate_pair(paired_validators(client, message_path, 'post'), body)
    event_contract = paired_validators(client, message_path, 'post', 200, 'text/event-stream')
    for _ in range(2):
        response = client.post(session_path + '/messages', json=body,
            headers={'Idempotency-Key': 'message', 'Accept': 'text/event-stream'})
        assert response.status_code == 200
        events = [json.loads(line[6:]) for line in response.text.splitlines() if line.startswith('data: ')]
        for event in events:
            validate_pair(event_contract, event)
        if domain == 'agent-lab':
            assert events[-1]['type'] == 'done'
        else:
            assert len(events) == 1 and events[0]['error_code'] == 'MODEL_RUNTIME_DISABLED'
    after = client.get(session_path).json()
    validate_pair(detail_contract, after)
    assert [m['role'] for m in after['messages']] == (['user', 'assistant'] if domain == 'agent-lab' else ['user'])
    if domain == 'agent-lab':
        assert after['messages'][-1]['generation'] == 'local_demo'
    else:
        assert len(after['exchanges']) == 1 and after['exchanges'][0]['status'] == 'failed'


@pytest.mark.parametrize('domain', ['agent-lab', 'agent-runtime'])
@pytest.mark.parametrize('resource,field,parent', [
    ('models', 'provider_profile_id', 'providers'),
    ('agents', 'model_profile_id', 'models'),
    ('sessions', 'agent_profile_id', 'agents'),
])
def test_cross_domain_ids_rejected_in_schema_and_http(client, domain, resource, field, parent):
    other = 'agent-runtime' if domain == 'agent-lab' else 'agent-lab'
    own, requests = make_stack(client, domain)
    foreign, _ = make_stack(client, other)
    body = {**requests[resource], field: foreign[parent]['id']}
    path = f'/api/local/{domain}/{resource}'
    for check in paired_validators(client, path, 'post'):
        assert not check.is_valid(body)
    response = client.post(path, json=body, headers={'Idempotency-Key': 'cross-domain'})
    assert response.status_code == 422 and response.json()['error']['code'] == 'VALIDATION_ERROR'
    assert client.get(path).json()['items'] == [own[resource]]


@pytest.mark.parametrize('kind,enabled,gate,ref,state', [
    ('openai_compatible', False, False, None, 'disabled'),
    ('anthropic', True, False, None, 'adapter_not_implemented'),
    ('openai_compatible', True, False, None, 'blocked_by_runtime_gate'),
    ('openai_compatible', True, True, None, 'credential_reference_missing'),
    ('openai_compatible', True, True, 'keychain://harnessagent/test', 'ready_to_attempt'),
])
def test_readiness_contract_is_not_a_provider_probe(client, kind, enabled, gate, ref, state):
    body = {'name': 'Readiness', 'type': kind, 'base_url': 'https://example.invalid', 'enabled': enabled}
    if ref:
        body['credential_ref'] = ref
    response = client.post('/api/local/agent-runtime/providers', json=body, headers={'Idempotency-Key': 'readiness'})
    assert response.status_code == 201
    # This fixture changes only the in-memory gate for a metadata GET; the sentinels forbid transport/credentials.
    client.app.state.service.agent_runtime._runtime_enabled = gate
    readiness = client.get('/api/local/agent-runtime/providers/' + response.json()['id'] + '/readiness')
    assert readiness.status_code == 200 and readiness.json()['state'] == state
    assert readiness.json()['network_calls'] == 0
    validate_pair(paired_validators(client, '/api/local/agent-runtime/providers/{provider_id}/readiness', 'get', 200), readiness.json())


def test_definition_registration_is_atomic_strict_and_does_not_mutate_source():
    from backend.openapi_contracts import register_definitions
    source = {'$defs': {'item': {'type': 'string'}, 'container': {
        'description': 'Literal #/$defs/item remains documentation',
        'type': 'array', 'items': {'$ref': '#/$defs/item'}}}}
    saved = copy.deepcopy(source)
    document = {}
    register_definitions(document, source, 'one_')
    register_definitions(document, source, 'two_')
    assert source == saved
    defs = document['components']['schemas']
    assert defs['one_container']['items']['$ref'] == '#/components/schemas/one_item'
    assert defs['two_container']['items']['$ref'] == '#/components/schemas/two_item'
    assert defs['one_container']['description'] == source['$defs']['container']['description']
    snapshot = copy.deepcopy(document)
    register_definitions(document, source, 'one_')
    assert document == snapshot
    with pytest.raises(ValueError, match='OPENAPI_SCHEMA_COLLISION:one_item'):
        register_definitions(document, {'$defs': {'new': {'type': 'number'}, 'item': {'type': 'integer'}}}, 'one_')
    assert document == snapshot
    register_definitions(document, {'$defs': {'bool': {'const': True}}})
    with pytest.raises(ValueError, match='OPENAPI_SCHEMA_COLLISION:bool'):
        register_definitions(document, {'$defs': {'bool': {'const': 1}}})


def test_all_registered_definitions_survive_final_document(monkeypatch):
    import backend.app as app_module
    original = app_module.register_definitions
    observations = []
    def observe(document, contract, namespace=''):
        original(document, contract, namespace)
        observations.append({namespace + name: copy.deepcopy(document['components']['schemas'][namespace + name])
                             for name in contract['$defs']})
    monkeypatch.setattr(app_module, 'register_definitions', observe)
    document = app_module.create_app(run_worker=False).openapi()
    assert len(observations) == 21
    for definitions in observations:
        for name, value in definitions.items():
            assert document['components']['schemas'][name] == value, name
            Draft202012Validator.check_schema(value)


def test_all_dynamic_refs_resolve_and_dangling_refs_are_rejected(client):
    from backend.openapi_contracts import assert_local_references
    document = client.get('/openapi.json').json()
    assert_local_references(document)
    broken = copy.deepcopy(document)
    broken['components']['schemas']['broken'] = {'$ref': '#/components/schemas/missing'}
    with pytest.raises(ValueError, match='OPENAPI_DANGLING_REFERENCE'):
        assert_local_references(broken)
    broken['components']['schemas']['broken'] = {'$ref': 'https://example.invalid/schema.json'}
    with pytest.raises(ValueError, match='OPENAPI_NONLOCAL_REFERENCE'):
        assert_local_references(broken)


@pytest.mark.parametrize('domain,id_prefix', [('agent-lab', 'chs'), ('agent-runtime', 'rts')])
def test_missing_session_detail_has_no_placeholder_data(client, domain, id_prefix):
    path = f'/api/local/{domain}/sessions'
    missing = client.get(path + '/' + id_prefix + '_' + '0' * 32)
    assert missing.status_code == 404 and missing.json()['error']['code'] == 'NOT_FOUND'
    assert client.get(path).json()['items'] == []


def test_missing_readiness_does_not_probe_or_create_provider(client):
    path = '/api/local/agent-runtime/providers'
    missing = client.get(path + '/rtp_' + '0' * 32 + '/readiness')
    assert missing.status_code == 404 and missing.json()['error']['code'] == 'NOT_FOUND'
    assert client.get(path).json()['items'] == []
