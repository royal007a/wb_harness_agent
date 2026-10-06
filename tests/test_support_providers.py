"""HA-0090: synthetic credentials/transport only; never reads operator credentials."""
import asyncio
import json
import os

import httpx
import pytest
from fastapi.testclient import TestClient

from backend.analysis import Problem
from backend.app import create_app
from backend.store import Store, dumps
from backend.support_providers import ARK_BASE, CredentialVault, SupportProviders


@pytest.fixture
def providers(tmp_path, monkeypatch):
    key = tmp_path / 'master'
    key.write_bytes(os.urandom(32))
    key.chmod(0o600)
    monkeypatch.setenv('HARNESS_SUPPORT', 'enabled')
    monkeypatch.setenv('HARNESS_SUPPORT_MASTER_KEY_FILE', str(key))
    store = Store(tmp_path / 'state.db')
    service = SupportProviders(store)
    yield service
    store.close()


def create(service, **kw):
    return service.save({'name': 'Offline probe', 'api_key': 'synthetic-secret-HA80', 'auto_probe': False, **kw})


class Body(httpx.AsyncByteStream):
    def __init__(self, value):
        self.value = value
    async def __aiter__(self):
        yield json.dumps(self.value).encode()


def response(status=200):
    return httpx.Response(status, stream=Body({'choices': [{'finish_reason': 'stop', 'message': {'content': 'OK'}}],
                         'usage': {'prompt_tokens': 12, 'completion_tokens': 1}}))


def test_secret_encrypted_redacted_bound_to_identity(providers):
    doc = create(providers)
    other = create(providers)
    raw = providers.store.db.execute('SELECT ciphertext FROM support_providers WHERE id=?', (doc['id'],)).fetchone()[0]
    assert b'synthetic-secret' not in raw
    assert 'synthetic-secret' not in dumps(providers.listing())
    assert 'ciphertext' not in dumps(doc)
    assert providers.vault.decrypt(doc['id'], raw) == 'synthetic-secret-HA80'
    with pytest.raises(Problem, match='凭证存储'):
        providers.vault.decrypt(other['id'], raw)
    providers.save({'api_key': 'rotated-synthetic-secret'}, doc['id'])
    row = providers.store.db.execute('SELECT ciphertext FROM support_providers WHERE id=?', (doc['id'],)).fetchone()
    assert row[0] != raw
    assert providers.vault.decrypt(doc['id'], row[0]) == 'rotated-synthetic-secret'


@pytest.mark.parametrize('kind', ['missing', 'permissions', 'symlink', 'invalid'])
def test_master_key_fails_closed(providers, tmp_path, kind):
    path = providers.vault.path
    if kind == 'missing':
        path.unlink()
    elif kind == 'permissions':
        path.chmod(0o644)
    elif kind == 'invalid':
        path.write_bytes(b'bad')
    else:
        link = tmp_path / 'link'
        link.symlink_to(path)
        providers.vault = CredentialVault(link)
    with pytest.raises(Problem) as exc:
        create(providers)
    assert exc.value.code == 'SUPPORT_KEY_UNAVAILABLE'
    assert providers.listing() == []


@pytest.mark.parametrize('patch', [
    {'base_url': 'http://127.0.0.1'}, {'base_url': ARK_BASE + '?key=secret'},
    {'base_url': 'https://example.com'}, {'enabled': 1}, {'probe_interval_seconds': True},
    {'probe_interval_seconds': 1}, {'api_key': 'has space secret'}, {'unknown': 'secret'},
])
def test_invalid_config_zero_writes(providers, patch):
    with pytest.raises(Problem):
        create(providers, **patch)
    assert providers.listing() == []


def test_probe_real_transport_boundary_redaction_daily_cap(providers):
    doc = create(providers)
    calls = []
    async def handle(request):
        calls.append(request)
        assert request.headers['authorization'] == 'Bearer synthetic-secret-HA80'
        assert request.headers['accept-encoding'] == 'identity'
        body = json.loads(request.content)
        assert body['max_completion_tokens'] == 32 and body['stream'] is False
        assert 'max_tokens' not in body and body['thinking'] == {'type': 'disabled'}
        return response()
    providers.transport = httpx.MockTransport(handle)
    result = asyncio.run(providers.probe(doc['id']))
    assert result['state'] == 'reachable' and result['input_tokens'] == 12
    assert len(calls) == 1 and 'OK' not in dumps(providers.get(doc['id']))
    providers.store.db.execute('UPDATE support_probe_days SET calls=96')
    with pytest.raises(Problem) as exc:
        asyncio.run(providers.probe(doc['id']))
    assert exc.value.code == 'SUPPORT_PROBE_LIMIT' and len(calls) == 1


def test_auth_failure_no_secret_or_body_persisted(providers):
    doc = create(providers)
    providers.transport = httpx.MockTransport(lambda request: httpx.Response(401, json={'secret': 'UPSTREAM_PRIVATE'}))
    result = asyncio.run(providers.probe(doc['id']))
    assert result['code'] == 'SUPPORT_PROVIDER_AUTH'
    assert 'UPSTREAM_PRIVATE' not in dumps(providers.listing())
    assert providers.busy == set()


def test_scheduler_runs_without_manual_request_and_stops(providers):
    doc = create(providers, auto_probe=True)
    calls = []
    async def handle(request):
        calls.append(request)
        return response()
    providers.transport = httpx.MockTransport(handle)
    async def scenario():
        providers.start()
        for _ in range(100):
            if providers.get(doc['id'])['health']['state'] == 'reachable':
                break
            await asyncio.sleep(.01)
        assert len(calls) == 1
        await providers.probe(doc['id'], automatic=True)
        assert len(calls) == 1  # persisted due time prevents duplicate scheduling
        await providers.close()
        assert providers.task.done()
    asyncio.run(scenario())


def test_probe_cancel_unlocks_and_records_unknown(providers):
    doc = create(providers)
    async def scenario():
        started = asyncio.Event()
        async def handle(request):
            started.set()
            await asyncio.Event().wait()
        providers.transport = httpx.MockTransport(handle)
        task = asyncio.create_task(providers.probe(doc['id']))
        await started.wait()
        with pytest.raises(Problem) as exc:
            providers.save({'enabled': False}, doc['id'])
        assert exc.value.code == 'SUPPORT_PROVIDER_BUSY'
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert providers.busy == set()
        assert providers.get(doc['id'])['health']['code'] == 'SUPPORT_PROBE_INTERRUPTED'
    asyncio.run(scenario())


def test_http_transport_guard_and_redaction(providers, tmp_path):
    with TestClient(create_app(tmp_path / 'http.db', run_worker=False), base_url='http://localhost') as client:
        body = {'name': 'synthetic', 'api_key': 'synthetic-secret-HA80', 'auto_probe': False}
        blocked = client.post('/api/local/support/providers', json=body,
                              headers={'x-forwarded-prefix': '/harness', 'x-forwarded-proto': 'http'})
        assert blocked.status_code == 403
        saved = client.post('/api/local/support/providers', json=body)
        assert saved.status_code == 201 and 'synthetic-secret' not in saved.text
        assert saved.json()['has_key'] is True
        listing = client.get('/api/local/support/providers')
        assert 'synthetic-secret' not in listing.text and 'ciphertext' not in listing.text
        ident = saved.json()['id']
        assert client.put('/api/local/support/providers/' + ident, json={'enabled': False}).status_code == 200
        assert client.post('/api/local/support/providers/' + ident + '/probe', json={}).status_code == 409
        assert client.delete('/api/local/support/providers/' + ident).status_code == 200
