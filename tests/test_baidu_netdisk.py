import json
from datetime import datetime, timedelta, timezone
from urllib.parse import parse_qs, urlparse

import pytest
from fastapi.testclient import TestClient

from backend.app import create_app
from backend.analysis import Problem
from backend.baidu_netdisk import (AUTHORIZATION_ENDPOINT, CLIENT_SECRET_ACCOUNT, REDIRECT_URI,
                                   TOKEN_ACCOUNT, TOKEN_ENDPOINT)
from backend.store import dumps


class MemorySecrets:
    def __init__(self, values=()):
        self.values = dict(values)

    def get(self, account):
        return self.values.get(account)

    def set(self, account, value):
        self.values[account] = value

    def delete(self, account):
        return self.values.pop(account, None) is not None


class FailingTokenWriteSecrets(MemorySecrets):
    def set(self, account, value):
        if account == TOKEN_ACCOUNT:
            raise Problem('CREDENTIAL_STORE_UNAVAILABLE', '凭证库不可用。', 503)
        super().set(account, value)


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv('HARNESS_BAIDUPAN_CLIENT_ID', 'test-client-id-123')
    app = create_app(tmp_path / 'test.db', run_worker=False)
    with TestClient(app, base_url='http://127.0.0.1') as client:
        connector = app.state.service.baidu_netdisk
        connector.secrets = MemorySecrets([(CLIENT_SECRET_ACCOUNT, 'client-secret-for-tests')])
        connector.http_post = lambda url, data: {
            'access_token': 'access-token-for-tests', 'refresh_token': 'refresh-token-for-tests',
            'expires_in': 3600, 'scope': 'basic,netdisk'}
        yield client


def authorization(client, key='authorization-key'):
    response = client.post('/api/local/connectors/baidu-netdisk/authorization', json={},
                           headers={'Idempotency-Key': key})
    assert response.status_code == 201, response.text
    return response.json()


def state_from(payload):
    parsed = urlparse(payload['authorization_url'])
    assert parsed.scheme == 'https' and parsed.netloc == 'openapi.baidu.com'
    assert parsed.path == '/oauth/2.0/authorize'
    query = parse_qs(parsed.query)
    assert query['response_type'] == ['code']
    assert query['redirect_uri'] == [REDIRECT_URI]
    assert query['scope'] == ['basic,netdisk']
    return query['state'][0]


def test_status_requires_public_config_and_keychain_secret(tmp_path, monkeypatch):
    monkeypatch.delenv('HARNESS_BAIDUPAN_CLIENT_ID', raising=False)
    app = create_app(tmp_path / 'test.db', run_worker=False)
    with TestClient(app, base_url='http://127.0.0.1') as client:
        connector = app.state.service.baidu_netdisk
        connector.secrets = MemorySecrets()
        response = client.get('/api/local/connectors/baidu-netdisk')
        assert response.status_code == 200
        assert response.json() == {'provider': 'baidu_netdisk', 'status': 'not_configured',
                                   'client_id_configured': False, 'redirect_uri': REDIRECT_URI,
                                   'credential_ref': 'keychain:HarnessAgent.BaiduNetdisk/oauth-token:default',
                                   'has_token': False, 'data_access_enabled': False}
        denied = client.post('/api/local/connectors/baidu-netdisk/authorization', json={},
                             headers={'Idempotency-Key': 'missing-config'})
        assert denied.status_code == 409 and denied.json()['error']['code'] == 'CONNECTOR_NOT_CONFIGURED'


def test_authorization_state_is_one_time_and_never_persisted_raw(client):
    first = authorization(client)
    second = authorization(client)
    assert second == first
    state = state_from(first)
    assert 'client-secret-for-tests' not in first['authorization_url']
    store = client.app.state.service.store
    with store.lock:
        persisted = '\n'.join(row[0] for row in store.db.execute('SELECT doc FROM oauth_attempts'))
    assert state not in persisted
    assert 'client-secret-for-tests' not in persisted
    assert 'access-token-for-tests' not in persisted
    complete = client.get('/api/local/connectors/baidu-netdisk/callback', params={'code': 'code-once', 'state': state})
    assert complete.status_code == 200
    assert '授权已完成' in complete.text
    assert 'access-token-for-tests' not in complete.text
    replay = client.get('/api/local/connectors/baidu-netdisk/callback', params={'code': 'code-again', 'state': state})
    assert replay.status_code == 409 and replay.json()['error']['code'] == 'AUTHORIZATION_STATE_USED'
    status = client.get('/api/local/connectors/baidu-netdisk').json()
    assert status['status'] == 'connected' and status['has_token'] is True and status['data_access_enabled'] is False


def test_callback_rejects_mismatch_expiry_and_provider_denial(client):
    invalid = client.get('/api/local/connectors/baidu-netdisk/callback', params={'code': 'anything', 'state': 'x' * 40},
                         headers={'Sec-Fetch-Site': 'cross-site'})
    assert invalid.status_code == 400 and invalid.json()['error']['code'] == 'AUTHORIZATION_STATE_INVALID'
    payload = authorization(client, 'denied')
    denied = client.get('/api/local/connectors/baidu-netdisk/callback',
                        params={'error': 'access_denied', 'state': state_from(payload)})
    assert denied.status_code == 200 and '授权未完成' in denied.text
    expired = authorization(client, 'expired')
    connector = client.app.state.service.baidu_netdisk
    connector.clock = lambda: datetime.now(timezone.utc) + timedelta(hours=1)
    response = client.get('/api/local/connectors/baidu-netdisk/callback',
                          params={'code': 'late-code', 'state': state_from(expired)})
    assert response.status_code == 400 and response.json()['error']['code'] == 'AUTHORIZATION_STATE_EXPIRED'


def test_token_response_refresh_disconnect_and_redaction(client):
    connector = client.app.state.service.baidu_netdisk
    calls = []
    def post(url, data):
        calls.append((url, dict(data)))
        assert url == TOKEN_ENDPOINT
        if data['grant_type'] == 'authorization_code':
            return {'access_token': 'initial-access-token', 'refresh_token': 'initial-refresh-token', 'expires_in': 60}
        return {'access_token': 'rotated-access-token', 'refresh_token': 'rotated-refresh-token', 'expires_in': 3600}
    connector.http_post = post
    payload = authorization(client, 'refresh')
    state = state_from(payload)
    response = client.get('/api/local/connectors/baidu-netdisk/callback', params={'code': 'code-for-refresh', 'state': state})
    assert response.status_code == 200
    raw = connector.secrets.get(TOKEN_ACCOUNT)
    record = json.loads(raw)
    record['expires_at'] = (datetime.now(timezone.utc) - timedelta(seconds=1)).isoformat()
    connector.secrets.set(TOKEN_ACCOUNT, dumps(record))
    refreshed = connector.refresh_for_verification()
    assert refreshed == {'provider': 'baidu_netdisk', 'refreshed': True, 'status': 'connected',
                         'has_token': True, 'data_access_enabled': False}
    assert calls[-1][1]['grant_type'] == 'refresh_token'
    assert 'initial-refresh-token' not in client.get('/api/local/connectors/baidu-netdisk').text
    disconnected = client.post('/api/local/connectors/baidu-netdisk:disconnect', json={},
                               headers={'Idempotency-Key': 'disconnect'})
    assert disconnected.status_code == 200 and disconnected.json()['has_token'] is False
    assert client.post('/api/local/connectors/baidu-netdisk:disconnect', json={},
                       headers={'Idempotency-Key': 'disconnect'}).json() == disconnected.json()


def test_keychain_token_write_failure_is_safe_and_audited(client):
    connector = client.app.state.service.baidu_netdisk
    connector.secrets = FailingTokenWriteSecrets([(CLIENT_SECRET_ACCOUNT, 'client-secret-for-tests')])
    payload = authorization(client, 'keychain-write-failure')
    response = client.get('/api/local/connectors/baidu-netdisk/callback',
                          params={'code': 'code-keychain-write', 'state': state_from(payload)})
    assert response.status_code == 503
    assert response.json()['error']['code'] == 'CREDENTIAL_STORE_UNAVAILABLE'
    assert 'access-token-for-tests' not in response.text
    with connector.store.lock:
        stored = '\n'.join(row[0] for row in connector.store.db.execute('SELECT doc FROM oauth_attempts'))
    assert 'keychain-write-failure' not in stored
    assert 'access-token-for-tests' not in stored


@pytest.mark.parametrize(('key', 'token'), [
    ('bad-none', None), ('bad-empty', {}),
    ('bad-expiry', {'access_token': 'x', 'refresh_token': 'y', 'expires_in': 1}),
    ('bad-access-length', {'access_token': 'x' * 257, 'refresh_token': 'y', 'expires_in': 3600}),
])
def test_reject_bad_token_response_without_persisting_token(client, key, token):
    connector = client.app.state.service.baidu_netdisk
    connector.http_post = lambda url, data: token
    payload = authorization(client, key)
    result = client.get('/api/local/connectors/baidu-netdisk/callback',
                        params={'code': 'bad-code', 'state': state_from(payload)})
    assert result.status_code == 502
    assert connector.secrets.get(TOKEN_ACCOUNT) is None


def test_http_boundary_and_request_shape(client):
    assert client.post('/api/local/connectors/baidu-netdisk/authorization', json={'extra': 1},
                       headers={'Idempotency-Key': 'shape'}).status_code == 422
    assert client.post('/api/local/connectors/baidu-netdisk/authorization', json={}).status_code == 422
    assert client.get('/api/local/connectors/baidu-netdisk', headers={'Host': 'evil.example'}).status_code == 403
    assert client.get('/api/local/connectors/baidu-netdisk/callback', headers={'Origin': 'https://evil.example'}).status_code == 403
    spec = client.get('/openapi.json').json()
    assert spec['paths']['/api/local/connectors/baidu-netdisk']['get']['responses']['200']['content']['application/json']['schema'] == {
        '$ref': '#/components/schemas/connection_status'}
    assert spec['paths']['/api/local/connectors/baidu-netdisk/authorization']['post']['responses']['201']['content']['application/json']['schema'] == {
        '$ref': '#/components/schemas/authorization_start'}


def test_oauth_transport_never_uses_environment_proxy(client, monkeypatch):
    options = {}
    class Response:
        def raise_for_status(self):
            return None
        def json(self):
            return {'access_token': 'access-token-for-tests', 'refresh_token': 'refresh-token-for-tests', 'expires_in': 3600}
    class DirectClient:
        def __init__(self, **kwargs):
            options.update(kwargs)
        def __enter__(self):
            return self
        def __exit__(self, *args):
            return False
        def post(self, url, data):
            assert url == TOKEN_ENDPOINT and data == {'grant_type': 'refresh_token'}
            return Response()
    monkeypatch.setattr('backend.baidu_netdisk.httpx.Client', DirectClient)
    connector = client.app.state.service.baidu_netdisk
    connector._http_post(TOKEN_ENDPOINT, {'grant_type': 'refresh_token'})
    assert options['trust_env'] is False and options['follow_redirects'] is False
