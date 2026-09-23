from fastapi.testclient import TestClient

from backend.app import create_app


def policy(**overrides):
    value = {
        'allowed_tools': ['resource.inspect', 'artifact.publish'],
        'allowed_domains': ['example.com'],
        'max_input_tokens': 1000,
        'max_cost_minor': 10,
        'provider_admitted': False,
    }
    value.update(overrides)
    return value


def check(client, action, **overrides):
    return client.post('/api/local/pi-contract-pipeline/security-check', json={'action': action, 'policy': policy(**overrides)}, headers={'Idempotency-Key': 'guard-' + str(abs(hash(repr(action))))})


def test_guard_is_metadata_only_and_fail_closed(tmp_path):
    with TestClient(create_app(tmp_path / 'guard.db', False), base_url='http://127.0.0.1') as client:
        allowed = check(client, {'phase': 'tool_call', 'tool': 'resource.inspect', 'estimated_tokens': 2})
        assert allowed.status_code == 200 and allowed.json()['decision'] == 'allow'
        assert allowed.json()['model_calls'] == allowed.json()['external_calls'] == 0
        for action in [
            {'phase': 'tool_call', 'tool': 'unknown.tool'},
            {'phase': 'tool_call', 'tool': 'resource.inspect', 'path': '../.ssh/id_rsa'},
            {'phase': 'tool_call', 'tool': 'resource.inspect', 'url': 'https://evil.example.net'},
            {'phase': 'tool_call', 'tool': 'artifact.publish', 'content': '手机号 13812345678'},
            {'phase': 'tool_call', 'tool': 'resource.inspect', 'estimated_tokens': 1001},
            {'phase': 'provider_request', 'estimated_tokens': 1},
        ]:
            result = check(client, action)
            assert result.status_code == 200 and result.json()['decision'] == 'deny', action
            assert result.json()['model_calls'] == result.json()['external_calls'] == 0


def test_guard_allows_explicit_provider_admission_and_is_idempotent(tmp_path):
    with TestClient(create_app(tmp_path / 'guard-admit.db', False), base_url='http://127.0.0.1') as client:
        body = {'action': {'phase': 'provider_request', 'estimated_tokens': 10, 'estimated_cost_minor': 1}, 'policy': policy(provider_admitted=True)}
        headers = {'Idempotency-Key': 'provider-admit'}
        first = client.post('/api/local/pi-contract-pipeline/security-check', json=body, headers=headers)
        again = client.post('/api/local/pi-contract-pipeline/security-check', json=body, headers=headers)
        assert first.status_code == again.status_code == 200
        assert first.json() == again.json() and first.json()['decision'] == 'allow'


def test_guard_contract_rejects_unknown_fields(tmp_path):
    with TestClient(create_app(tmp_path / 'guard-invalid.db', False), base_url='http://127.0.0.1') as client:
        response = client.post('/api/local/pi-contract-pipeline/security-check', json={'action': {'phase': 'tool_call', 'extra': 1}, 'policy': policy()}, headers={'Idempotency-Key': 'guard-invalid'})
        assert response.status_code == 422
        assert response.json()['error']['code'] == 'VALIDATION_ERROR'
