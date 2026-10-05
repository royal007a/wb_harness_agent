import json
import threading
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from backend.app import create_app
from backend.analysis import Problem


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv('HARNESS_DSH_LOCAL', 'enabled')
    monkeypatch.setenv('HARNESS_DSH_RUN_ROOT', str(tmp_path / 'owned-runs'))
    monkeypatch.delenv('HARNESS_DSH_REAL_ENABLED', raising=False)
    with TestClient(create_app(tmp_path / 'test.db', run_worker=False), base_url='http://localhost') as c:
        yield c


def create(client, **changes):
    body = {'objective': '核对付款条件并引用条款。', 'document': 'SYNTHETIC_PRIVATE_77：验收后30天付款，逾期双方协商。',
            'public_data_confirmed': True, 'mode': 'integration_probe', **changes}
    response = client.post('/api/local/dsh/runs', json=body, headers={'Idempotency-Key': 'key77'})
    assert response.status_code == 201, response.text
    return response.json()['initial_run']['id']


def test_actual_dsh_two_model_calls_and_tool_result_no_event_content(client):
    ident = create(client)
    runtime = client.app.state.service.dsh
    runtime.execute(ident)
    detail = client.get('/api/local/dsh/runs/' + ident).json()
    assert detail['run']['status'] == 'succeeded', detail
    assert detail['budget']['calls'] == 2
    assert detail['budget']['spent'] == 430
    events = client.get('/api/local/dsh/runs/' + ident + '/events').json()['items']
    assert 'SYNTHETIC_PRIVATE_77' not in json.dumps(events)
    assert sum(e['event_type'] == 'dsh.tool.completed' for e in events) == 1
    assert any(e['event_type'] == 'dsh.observation' for e in events)
    artifact = detail['artifacts'][0]
    body = runtime.store.db.execute('SELECT body FROM artifacts WHERE id=?', (artifact['id'],)).fetchone()[0]
    assert b'SYNTHETIC_PRIVATE_77' in body
    assert b'clause-1' in body
    assert not list(Path(__import__('os').environ['HARNESS_DSH_RUN_ROOT']).iterdir())
    # A terminal replay cannot make another Provider request or undo success.
    snapshot = runtime.ledger.snapshot(ident)
    runtime.execute(ident)
    runtime.cancel(ident)
    assert runtime.detail(ident)['run']['status'] == 'succeeded'
    assert runtime.ledger.snapshot(ident) == snapshot


def test_real_provider_is_explicitly_blocked_not_synthetic_fallback(client):
    r = client.post('/api/local/dsh/runs', json={'objective': 'x', 'document': 'x',
        'public_data_confirmed': True, 'mode': 'real_provider'}, headers={'Idempotency-Key': 'real'})
    assert r.status_code == 409
    assert r.json()['error']['code'] == 'DSH_PROVIDER_NOT_ADMITTED'
    assert client.get('/api/local/dsh/runs').json() == {'items': []}


def test_budget_blocks_before_first_model_request(client):
    ident = create(client, token_limit=1000)
    runtime = client.app.state.service.dsh
    async def forbidden(*args):
        pytest.fail('Provider must not be called')
    runtime.send_probe = forbidden
    runtime.execute(ident)
    assert runtime.detail(ident)['run']['exit_reason'] == 'BUSINESS_TOKEN_BUDGET_EXHAUSTED'
    assert runtime.ledger.snapshot(ident)['calls'] == 0


def test_cancel_while_provider_waits_never_publishes(client):
    ident = create(client)
    runtime = client.app.state.service.dsh
    started = threading.Event()
    original = runtime.send_probe
    async def slow(payload, limit):
        import asyncio
        started.set()
        await asyncio.sleep(.8)
        return await original(payload, limit)
    runtime.send_probe = slow
    worker = threading.Thread(target=runtime.execute, args=(ident,))
    worker.start()
    assert started.wait(10)
    runtime.cancel(ident)
    worker.join(10)
    assert not worker.is_alive()
    detail = runtime.detail(ident)
    assert detail['run']['status'] == 'cancelled'
    assert not detail['artifacts']


def test_provider_failure_is_terminal_and_no_retry(client):
    ident = create(client)
    runtime = client.app.state.service.dsh
    calls = []
    async def failure(*args):
        calls.append(1)
        raise Problem('DSH_PROVIDER_HTTP_ERROR', 'SECRET_DO_NOT_PERSIST', 502)
    runtime.send_probe = failure
    runtime.execute(ident)
    detail = runtime.detail(ident)
    assert detail['run']['exit_reason'] == 'DSH_PROVIDER_HTTP_ERROR'
    assert detail['budget']['status'] == 'usage_unknown'
    assert calls == [1]
    assert 'SECRET_DO_NOT_PERSIST' not in json.dumps(runtime.store.events(ident))
    assert not detail['artifacts']


def test_disabled_by_default(tmp_path, monkeypatch):
    monkeypatch.delenv('HARNESS_DSH_LOCAL', raising=False)
    with TestClient(create_app(tmp_path / 'off.db', run_worker=False), base_url='http://localhost') as c:
        assert c.get('/api/local/dsh/runtime').status_code == 409


@pytest.mark.parametrize('mutation', [
    {'objective': ' '}, {'document': '\n'}, {'public_data_confirmed': False},
    {'token_limit': 20000001}, {'timeout_seconds': 301}, {'mode': 'auto'}, {'unknown': True},
])
def test_invalid_requests_have_no_writes(client, mutation):
    store = client.app.state.service.store
    before = store.db.total_changes
    r = client.post('/api/local/dsh/runs', json={'objective': 'x', 'document': 'x',
        'mode': 'integration_probe', 'public_data_confirmed': True, **mutation}, headers={'Idempotency-Key': 'bad'})
    assert r.status_code == 422
    assert store.db.total_changes == before


def test_idempotency_replays_without_new_run_and_conflicts(client):
    first = create(client)
    store = client.app.state.service.store
    before = store.db.total_changes
    assert create(client) == first
    assert store.db.total_changes == before
    with pytest.raises(AssertionError):
        create(client, document='different')
    assert store.db.total_changes == before


def test_restart_stops_queued_without_provider_calls(client):
    ident = create(client)
    runtime = client.app.state.service.dsh
    runtime.recover()
    assert runtime.detail(ident)['run']['exit_reason'] == 'DSH_SERVER_RESTARTED'
    runtime.execute(ident)
    assert not runtime.detail(ident)['artifacts']


def test_subprocess_allowlist_removes_inherited_secret_and_injection(client, monkeypatch):
    import adapters.dsh as adapter
    monkeypatch.setenv('MODEL_SECRET_SENTINEL', 'PRIVATE_ENV_77')
    monkeypatch.setenv('NODE_OPTIONS', '--require=/should/not/exist')
    original = adapter.subprocess.Popen
    launches = []
    def observed(*args, **kwargs):
        launches.append(kwargs['env'])
        return original(*args, **kwargs)
    monkeypatch.setattr(adapter.subprocess, 'Popen', observed)
    ident = create(client)
    runtime = client.app.state.service.dsh
    runtime.execute(ident)
    assert runtime.detail(ident)['run']['status'] == 'succeeded'
    assert len(launches) == 1
    assert 'NODE_OPTIONS' not in launches[0] and 'MODEL_SECRET_SENTINEL' not in launches[0]
    assert 'ARK_API_KEY' not in launches[0]


@pytest.mark.parametrize('variant', ['usage', 'length', 'bash', 'no_evidence'])
def test_untrusted_provider_results_never_publish(client, variant):
    from backend.dsh_provider import parse_response
    ident = create(client)
    runtime = client.app.state.service.dsh
    async def malformed(*args):
        response = {'choices': [{'finish_reason': 'stop', 'message': {'content': 'PRIVATE_BAD_RESULT'}}],
                    'usage': {'prompt_tokens': 1, 'completion_tokens': 1, 'total_tokens': 2}}
        if variant == 'usage': response['usage']['total_tokens'] = 99
        if variant == 'length': response['choices'][0]['finish_reason'] = 'length'
        if variant == 'bash':
            response['choices'][0] = {'finish_reason': 'tool_calls', 'message': {'tool_calls': [
                {'id': 'call_bad', 'type': 'function', 'function': {'name': 'bash', 'arguments': '{"command":"bad"}'}}]}}
        return parse_response(response)
    runtime.send_probe = malformed
    runtime.execute(ident)
    detail = runtime.detail(ident)
    assert detail['run']['status'] == 'failed'
    assert not detail['artifacts']
    assert 'PRIVATE_BAD_RESULT' not in json.dumps(runtime.store.events(ident))


def test_http_boundaries_and_pagination(client):
    assert client.get('/api/local/dsh/runtime', headers={'Host': 'evil.example'}).status_code == 403
    assert client.post('/api/local/dsh/runs', json={}, headers={'Origin': 'https://evil.example'}).status_code == 403
    ident = create(client)
    assert client.get(f'/api/local/dsh/runs/{ident}/events?after=9223372036854775808').status_code == 422
    r = client.get(f'/api/local/dsh/runs/{ident}/events?after=1')
    assert r.json() == {'items': [], 'next_cursor': 1}


def test_real_route_uses_conservative_model_capacity_not_char_estimate(client, monkeypatch):
    monkeypatch.setenv('HARNESS_DSH_REAL_ENABLED', '1')
    monkeypatch.setenv('HARNESS_DSH_CREDENTIAL_REF', 'unit-reference')
    ident = create(client, mode='real_provider', token_limit=1200000)
    runtime = client.app.state.service.dsh
    runtime.credentials.resolve = lambda _: pytest.fail('insufficient reservation must not resolve credentials')
    runtime.execute(ident)
    assert runtime.detail(ident)['run']['exit_reason'] == 'BUSINESS_TOKEN_BUDGET_EXHAUSTED'
