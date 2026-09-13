"""Official Baidu OAuth connection boundary; never stores tokens in SQLite."""
import json
import os
import secrets
import base64
import hmac
from datetime import datetime, timedelta, timezone
from urllib.parse import urlencode

import httpx
import keyring
from keyring.errors import KeyringError, PasswordDeleteError

from .analysis import Problem, digest
from .store import dumps, now

PROVIDER = 'baidu_netdisk'
AUTHORIZATION_ENDPOINT = 'https://openapi.baidu.com/oauth/2.0/authorize'
TOKEN_ENDPOINT = 'https://openapi.baidu.com/oauth/2.0/token'
SCOPE = 'basic,netdisk'
REDIRECT_URI = 'http://127.0.0.1:8765/api/local/connectors/baidu-netdisk/callback'
KEYCHAIN_SERVICE = 'HarnessAgent.BaiduNetdisk'
CLIENT_SECRET_ACCOUNT = 'oauth-client-secret'
TOKEN_ACCOUNT = 'oauth-token:default'
ATTEMPT_TTL_SECONDS = 600


def utc_now():
    return datetime.now(timezone.utc)


class KeychainSecrets:
    """macOS Keychain wrapper. Values never leave this module except for HTTPS calls."""
    def get(self, account):
        try:
            return keyring.get_password(KEYCHAIN_SERVICE, account)
        except KeyringError as exc:
            raise Problem('CREDENTIAL_STORE_UNAVAILABLE', '无法访问本机凭证库。', 503) from exc

    def set(self, account, value):
        if not isinstance(value, str) or not value or len(value) > 8192:
            raise Problem('CREDENTIAL_INVALID', '凭证格式无效。')
        try:
            keyring.set_password(KEYCHAIN_SERVICE, account, value)
        except KeyringError as exc:
            raise Problem('CREDENTIAL_STORE_UNAVAILABLE', '无法写入本机凭证库。', 503) from exc

    def delete(self, account):
        try:
            keyring.delete_password(KEYCHAIN_SERVICE, account)
        except PasswordDeleteError:
            return False
        except KeyringError as exc:
            raise Problem('CREDENTIAL_STORE_UNAVAILABLE', '无法更新本机凭证库。', 503) from exc
        return True


class BaiduNetdiskConnector:
    def __init__(self, store, secrets_store=None, http_post=None, clock=utc_now):
        self.store = store
        self.secrets = secrets_store or KeychainSecrets()
        self.http_post = http_post or self._http_post
        self.clock = clock

    def client_id(self):
        value = os.environ.get('HARNESS_BAIDUPAN_CLIENT_ID', '').strip()
        return value if 8 <= len(value) <= 128 else None

    def _secret(self, account):
        value = self.secrets.get(account)
        return value if isinstance(value, str) and 1 <= len(value) <= 4096 else None

    def status(self):
        client_id = self.client_id()
        try:
            has_client_secret = bool(self._secret(CLIENT_SECRET_ACCOUNT))
            has_token = bool(self._secret(TOKEN_ACCOUNT))
        except Problem:
            has_client_secret = has_token = False
        configured = bool(client_id and has_client_secret)
        return {'provider': PROVIDER,
                'status': 'connected' if configured and has_token else ('ready' if configured else 'not_configured'),
                'client_id_configured': bool(client_id), 'redirect_uri': REDIRECT_URI,
                'credential_ref': 'keychain:' + KEYCHAIN_SERVICE + '/' + TOKEN_ACCOUNT,
                'has_token': has_token, 'data_access_enabled': False}

    def _state(self, nonce, idempotency_digest):
        secret = self._required_client_secret().encode()
        signed = hmac.digest(secret, (nonce + ':' + idempotency_digest).encode(), 'sha256')
        return nonce + '.' + base64.urlsafe_b64encode(signed).decode().rstrip('=')

    def authorization(self, db, key):
        if not isinstance(key, str) or not 1 <= len(key) <= 128:
            raise Problem('VALIDATION_ERROR', '必须提供 1–128 字符的 Idempotency-Key。', 422)
        if self.status()['status'] == 'not_configured':
            raise Problem('CONNECTOR_NOT_CONFIGURED', '请先配置 App Key 和本机 Keychain Client Secret。', 409)
        idempotency_digest = digest(key.encode())
        existing = self.store.oauth_attempt_by_idempotency(idempotency_digest)
        if existing:
            if existing['status'] != 'pending' or self.clock() >= datetime.fromisoformat(existing['expires_at'].replace('Z', '+00:00')):
                raise Problem('AUTHORIZATION_STATE_USED', '此授权请求已结束，请使用新的 Idempotency-Key 重试。', 409)
            state = self._state(existing['nonce'], idempotency_digest)
            return {'provider': PROVIDER,
                    'authorization_url': self._authorization_url(state), 'expires_at': existing['expires_at']}
        nonce = secrets.token_urlsafe(32)
        state = self._state(nonce, idempotency_digest)
        state_digest = digest(state.encode())
        expires_at = self.clock() + timedelta(seconds=ATTEMPT_TTL_SECONDS)
        attempt = {'id': 'oauth_' + state_digest, 'provider': PROVIDER, 'state_digest': state_digest,
                   'idempotency_digest': idempotency_digest, 'nonce': nonce,
                   'status': 'pending', 'created_at': now(),
                   'expires_at': expires_at.isoformat().replace('+00:00', 'Z'), 'completed_at': None,
                   'error_code': None}
        self.store.put_oauth_attempt(db, attempt)
        return {'provider': PROVIDER, 'authorization_url': self._authorization_url(state),
                'expires_at': attempt['expires_at']}

    def _authorization_url(self, state):
        query = urlencode({'response_type': 'code', 'client_id': self.client_id(), 'redirect_uri': REDIRECT_URI,
                           'scope': SCOPE, 'state': state})
        return AUTHORIZATION_ENDPOINT + '?' + query

    def _attempt(self, state):
        if not isinstance(state, str) or not 32 <= len(state) <= 256:
            raise Problem('AUTHORIZATION_STATE_INVALID', '授权状态无效。', 400)
        return self.store.oauth_attempt_by_state_digest(digest(state.encode()))

    def _set_attempt(self, attempt, *, status, error_code=None):
        with self.store.transaction() as db:
            current = self.store.oauth_attempt(attempt['id'])
            current.update(status=status, error_code=error_code,
                           completed_at=now() if status in {'connected', 'denied', 'failed', 'expired'} else None)
            self.store.put_oauth_attempt(db, current)
        return current

    def _consume_attempt(self, state):
        attempt = self._attempt(state)
        if attempt['status'] != 'pending':
            raise Problem('AUTHORIZATION_STATE_USED', '授权状态已使用或已结束。', 409)
        expires_at = datetime.fromisoformat(attempt['expires_at'].replace('Z', '+00:00'))
        if self.clock() >= expires_at:
            self._set_attempt(attempt, status='expired', error_code='AUTHORIZATION_STATE_EXPIRED')
            raise Problem('AUTHORIZATION_STATE_EXPIRED', '授权状态已过期，请重新发起连接。', 400)
        self._set_attempt(attempt, status='exchanging')
        return attempt

    def callback(self, code=None, state=None, error=None):
        attempt = self._consume_attempt(state)
        if error:
            self._set_attempt(attempt, status='denied', error_code='OAUTH_AUTHORIZATION_DENIED')
            return {'connected': False, 'message': '授权未完成；你可以关闭此页面并在工作台重新发起。'}
        if not isinstance(code, str) or not 1 <= len(code) <= 1024 or any(ch.isspace() for ch in code):
            self._set_attempt(attempt, status='failed', error_code='OAUTH_CODE_INVALID')
            raise Problem('OAUTH_CODE_INVALID', '授权回调缺少有效 code。', 400)
        try:
            token = self._exchange({'grant_type': 'authorization_code', 'code': code,
                                    'client_id': self.client_id(), 'client_secret': self._required_client_secret(),
                                    'redirect_uri': REDIRECT_URI})
            self._save_token(token)
        except Problem as exc:
            self._set_attempt(attempt, status='failed', error_code=exc.code)
            raise
        self._set_attempt(attempt, status='connected')
        return {'connected': True, 'message': '百度网盘授权已安全保存到本机凭证库。'}

    def _required_client_secret(self):
        value = self._secret(CLIENT_SECRET_ACCOUNT)
        if not self.client_id() or not value:
            raise Problem('CONNECTOR_NOT_CONFIGURED', 'OAuth 应用凭证未配置。', 409)
        return value

    def _http_post(self, url, data):
        if url != TOKEN_ENDPOINT:
            raise Problem('OAUTH_ENDPOINT_INVALID', 'OAuth 端点不在允许范围内。')
        try:
            # OAuth credentials must never follow an ambient HTTP(S)/SOCKS
            # proxy.  The endpoint is fixed and HTTPS, so use a direct client.
            with httpx.Client(timeout=httpx.Timeout(10), follow_redirects=False, trust_env=False) as client:
                response = client.post(url, data=data)
                response.raise_for_status()
                return response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise Problem('OAUTH_TOKEN_EXCHANGE_FAILED', '令牌服务不可用或响应无效。', 502) from exc

    def _exchange(self, data):
        response = self.http_post(TOKEN_ENDPOINT, data)
        if not isinstance(response, dict) or response.get('error'):
            raise Problem('OAUTH_TOKEN_EXCHANGE_FAILED', '令牌服务拒绝授权。', 502)
        access = response.get('access_token')
        refresh = response.get('refresh_token')
        expires = response.get('expires_in')
        if (not isinstance(access, str) or not 1 <= len(access) <= 256 or not isinstance(refresh, str)
                or not 1 <= len(refresh) <= 2048 or isinstance(expires, bool) or not isinstance(expires, int)
                or not 60 <= expires <= 315360000):
            raise Problem('OAUTH_TOKEN_RESPONSE_INVALID', '令牌响应不满足连接器契约。', 502)
        return {'access_token': access, 'refresh_token': refresh, 'expires_at':
                (self.clock() + timedelta(seconds=expires)).isoformat().replace('+00:00', 'Z'),
                'scope': response.get('scope') if isinstance(response.get('scope'), str) else ''}

    def _save_token(self, token):
        self.secrets.set(TOKEN_ACCOUNT, dumps(token))

    def _token(self):
        raw = self._secret(TOKEN_ACCOUNT)
        if not raw:
            raise Problem('CONNECTOR_NOT_AUTHORIZED', '尚未完成百度网盘授权。', 409)
        try:
            token = json.loads(raw)
        except (TypeError, ValueError) as exc:
            raise Problem('CREDENTIAL_INVALID', '本机授权凭证格式无效。', 409) from exc
        if not isinstance(token, dict):
            raise Problem('CREDENTIAL_INVALID', '本机授权凭证格式无效。', 409)
        return token

    def access_token(self):
        token = self._token()
        expires_at = token.get('expires_at')
        try:
            expires = datetime.fromisoformat(expires_at.replace('Z', '+00:00'))
        except (AttributeError, ValueError) as exc:
            raise Problem('CREDENTIAL_INVALID', '本机授权凭证已损坏。', 409) from exc
        if self.clock() + timedelta(seconds=60) < expires and isinstance(token.get('access_token'), str):
            return token['access_token']
        return self._refresh(token)['access_token']

    def _refresh(self, token):
        refresh_token = token.get('refresh_token')
        if not isinstance(refresh_token, str) or not 1 <= len(refresh_token) <= 2048:
            raise Problem('CREDENTIAL_INVALID', '本机授权凭证已损坏。', 409)
        refreshed = self._exchange({'grant_type': 'refresh_token', 'refresh_token': refresh_token,
                                    'client_id': self.client_id(), 'client_secret': self._required_client_secret()})
        self._save_token(refreshed)
        return refreshed

    def refresh_for_verification(self):
        """Perform one user-approved OAuth refresh; deliberately return no token material."""
        self._refresh(self._token())
        state = self.status()
        return {'provider': PROVIDER, 'refreshed': True, 'status': state['status'],
                'has_token': state['has_token'], 'data_access_enabled': state['data_access_enabled']}

    def disconnect(self):
        self.secrets.delete(TOKEN_ACCOUNT)
        return self.status()
