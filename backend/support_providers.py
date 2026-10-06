"""Customer-support provider registry. Secrets never enter JSON documents or receipts."""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import stat
import time
from urllib.parse import urlsplit

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
import httpx

from .analysis import Problem
from .store import dumps, now, uid

ARK_BASE = 'https://ark.cn-beijing.volces.com/api/coding/v3'
MAX_RESPONSE = 262144


def fail(code, status=422):
    return Problem(code, {
        'SUPPORT_DISABLED': '智能客服服务未启用。',
        'SUPPORT_KEY_UNAVAILABLE': '凭证存储不可用，请管理员检查主密钥。',
        'SUPPORT_PROVIDER_BUSY': '该 Provider 正在调用，请稍后重试。',
        'SUPPORT_PROBE_LIMIT': '今天的连通探测次数已达上限。',
    }.get(code, '智能客服请求未满足配置或安全约束。'), status)


class CredentialVault:
    """Provisioning owns key creation. Runtime never silently replaces a missing key."""
    def __init__(self, path):
        self.path = Path(path) if path else None

    def _cipher(self):
        if self.path is None:
            raise fail('SUPPORT_KEY_UNAVAILABLE', 503)
        try:
            fd = os.open(self.path, os.O_RDONLY | os.O_NOFOLLOW)
            with os.fdopen(fd, 'rb') as handle:
                info = os.fstat(handle.fileno())
                if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid() or info.st_mode & 0o077:
                    raise ValueError()
                key = handle.read(33)
                if len(key) != 32:
                    raise ValueError()
            return AESGCM(key)
        except (OSError, ValueError):
            raise fail('SUPPORT_KEY_UNAVAILABLE', 503) from None

    def encrypt(self, provider_id, secret):
        nonce = os.urandom(12)
        return nonce + self._cipher().encrypt(nonce, secret.encode(), provider_id.encode())

    def decrypt(self, provider_id, blob):
        try:
            return self._cipher().decrypt(blob[:12], blob[12:], provider_id.encode()).decode()
        except (InvalidTag, ValueError, UnicodeDecodeError):
            raise fail('SUPPORT_KEY_UNAVAILABLE', 503) from None


class SupportProviders:
    def __init__(self, store):
        self.store = store
        self.enabled = os.environ.get('HARNESS_SUPPORT') == 'enabled'
        self.vault = CredentialVault(os.environ.get('HARNESS_SUPPORT_MASTER_KEY_FILE'))
        self.allowed_bases = frozenset(os.environ.get('HARNESS_SUPPORT_BASE_URLS', ARK_BASE).split(','))
        self.busy = set()
        self.task = None
        self.stopping = asyncio.Event()
        self.transport = None  # injected only by offline tests
        with store.lock:
            store.db.executescript('''
                CREATE TABLE IF NOT EXISTS support_providers(
                    id TEXT PRIMARY KEY, doc TEXT NOT NULL, ciphertext BLOB NOT NULL);
                CREATE TABLE IF NOT EXISTS support_probe_days(
                    provider_id TEXT NOT NULL, day TEXT NOT NULL, calls INTEGER NOT NULL,
                    PRIMARY KEY(provider_id, day));
            ''')

    def require_enabled(self):
        if not self.enabled:
            raise fail('SUPPORT_DISABLED', 409)

    def _row(self, ident):
        row = self.store.db.execute('SELECT * FROM support_providers WHERE id=?', (ident,)).fetchone()
        if row is None:
            raise fail('SUPPORT_PROVIDER_NOT_FOUND', 404)
        return row

    def get(self, ident):
        with self.store.lock:
            return json.loads(self._row(ident)['doc'])

    def listing(self):
        with self.store.lock:
            return [json.loads(r[0]) for r in self.store.db.execute('SELECT doc FROM support_providers ORDER BY id')]

    def status(self):
        return {'enabled': self.enabled, 'credential_storage': 'sqlite_aes_256_gcm',
                'release': os.environ.get('HARNESS_RELEASE_COMMIT','development'),
                'automatic_probes_running': self.task is not None and not self.task.done(),
                'probe_daily_limit_per_provider': 96, 'probe_max_output_tokens': 32,
                'scope': 'single_trusted_administrator', 'provider_count': len(self.listing())}

    def save(self, body, ident=None):
        self.require_enabled()
        if not isinstance(body, dict) or set(body) - {
            'name', 'base_url', 'model', 'api_key', 'enabled', 'auto_probe', 'probe_interval_seconds'
        }:
            raise fail('SUPPORT_CONFIG_INVALID')
        with self.store.transaction() as db:
            old = self._row(ident) if ident else None
            ident = ident or uid('csp')
            if ident in self.busy:
                raise fail('SUPPORT_PROVIDER_BUSY', 409)
            previous = json.loads(old['doc']) if old else {}
            doc = {key: body.get(key, previous.get(key, default)) for key, default in (
                ('name', ''), ('base_url', ARK_BASE), ('model', 'doubao-seed-2.1-lite'),
                ('enabled', True), ('auto_probe', True), ('probe_interval_seconds', 900))}
            if any(not isinstance(doc[k], str) or not 1 <= len(doc[k]) <= size for k, size in (
                ('name', 100), ('base_url', 512), ('model', 120))):
                raise fail('SUPPORT_CONFIG_INVALID')
            try:
                url = urlsplit(doc['base_url'])
                port = url.port
            except ValueError:
                raise fail('SUPPORT_CONFIG_INVALID') from None
            if (doc['base_url'] not in self.allowed_bases or url.scheme != 'https' or not url.hostname
                    or url.username or url.password or url.query or url.fragment or port not in (None, 443)
                    or doc['base_url'].endswith('/')):
                raise fail('SUPPORT_ENDPOINT_DENIED', 403)
            if not re.fullmatch(r'[a-zA-Z0-9][a-zA-Z0-9_.:/-]{0,119}', doc['model']):
                raise fail('SUPPORT_CONFIG_INVALID')
            if any(type(doc[k]) is not bool for k in ('enabled', 'auto_probe')):
                raise fail('SUPPORT_CONFIG_INVALID')
            if type(doc['probe_interval_seconds']) is not int or not 300 <= doc['probe_interval_seconds'] <= 86400:
                raise fail('SUPPORT_CONFIG_INVALID')
            secret = body.get('api_key')
            if secret is not None:
                if not isinstance(secret, str) or not 8 <= len(secret) <= 2048 or not secret.isascii() or not secret.isprintable() or any(c.isspace() for c in secret):
                    raise fail('SUPPORT_KEY_INVALID')
                ciphertext = self.vault.encrypt(ident, secret)
            elif old:
                ciphertext = old['ciphertext']
            else:
                raise fail('SUPPORT_KEY_REQUIRED')
            doc.update(id=ident, has_key=True, created_at=previous.get('created_at', now()), updated_at=now(),
                       next_probe_at=previous.get('next_probe_at', 0),
                       health=previous.get('health', {'state': 'not_checked'}))
            if secret is not None or any(doc[k] != previous.get(k) for k in ('base_url', 'model')):
                doc['health'] = {'state': 'not_checked'}
                doc['next_probe_at'] = 0
            db.execute('INSERT INTO support_providers VALUES(?,?,?) ON CONFLICT(id) DO UPDATE SET doc=excluded.doc,ciphertext=excluded.ciphertext',
                       (ident, dumps(doc), ciphertext))
            return doc

    def delete(self, ident):
        self.require_enabled()
        with self.store.transaction() as db:
            self._row(ident)
            if ident in self.busy:
                raise fail('SUPPORT_PROVIDER_BUSY', 409)
            db.execute('DELETE FROM support_providers WHERE id=?', (ident,))
            # Keep aggregate daily counts: deletion cannot reset limits for this ID.
        return {'deleted': True, 'id': ident}

    async def request(self, ident, path, payload):
        """Last-mile secret resolution. No redirects, compression, ambient proxies or raw errors."""
        self.require_enabled()
        with self.store.lock:
            row = self._row(ident)
            doc = json.loads(row['doc'])
            if not doc['enabled'] or doc['base_url'] not in self.allowed_bases:
                raise fail('SUPPORT_PROVIDER_DISABLED', 409)
            secret = self.vault.decrypt(ident, row['ciphertext'])
        if path not in ('/chat/completions', '/embeddings', '/models'):
            raise fail('SUPPORT_ENDPOINT_DENIED', 403)
        try:
            async with httpx.AsyncClient(timeout=20, trust_env=False, follow_redirects=False, transport=self.transport) as client:
                async with client.stream('POST', doc['base_url'] + path, json=payload,
                        headers={'Authorization': 'Bearer ' + secret, 'Accept-Encoding': 'identity'}) as response:
                    if response.status_code != 200:
                        code = 'SUPPORT_PROVIDER_AUTH' if response.status_code in (401, 403) else 'SUPPORT_PROVIDER_HTTP'
                        raise fail(code, 502)
                    if 'content-encoding' in response.headers:
                        raise fail('SUPPORT_PROVIDER_ENCODING', 502)
                    raw = bytearray()
                    async for part in response.aiter_raw():
                        raw.extend(part)
                        if len(raw) > MAX_RESPONSE:
                            raise fail('SUPPORT_PROVIDER_LIMIT', 502)
            value = json.loads(raw)
            if not isinstance(value, dict):
                raise ValueError()
            return value
        except (httpx.HTTPError, TimeoutError):
            raise fail('SUPPORT_PROVIDER_UNAVAILABLE', 502) from None
        except (ValueError, UnicodeDecodeError, RecursionError):
            raise fail('SUPPORT_PROVIDER_INVALID', 502) from None

    async def probe(self, ident, *, automatic=False):
        self.require_enabled()
        with self.store.transaction() as db:
            doc = json.loads(self._row(ident)['doc'])
            if not doc['enabled']:
                raise fail('SUPPORT_PROVIDER_DISABLED', 409)
            if ident in self.busy:
                raise fail('SUPPORT_PROVIDER_BUSY', 409)
            if automatic and (not doc['auto_probe'] or doc['next_probe_at'] > time.time()):
                return doc['health']
            day = datetime.now(timezone.utc).date().isoformat()
            row = db.execute('SELECT calls FROM support_probe_days WHERE provider_id=? AND day=?', (ident, day)).fetchone()
            if row and row[0] >= 96:
                raise fail('SUPPORT_PROBE_LIMIT', 429)
            db.execute('INSERT INTO support_probe_days VALUES(?,?,1) ON CONFLICT(provider_id,day) DO UPDATE SET calls=calls+1', (ident, day))
            doc['next_probe_at'] = time.time() + doc['probe_interval_seconds']
            doc['health'] = {'state': 'checking', 'checked_at': now(), 'automatic': automatic}
            db.execute('UPDATE support_providers SET doc=? WHERE id=?', (dumps(doc), ident))
            self.busy.add(ident)
        started = time.monotonic()
        health = {'state': 'failed', 'code': 'SUPPORT_PROBE_INTERRUPTED', 'checked_at': now(), 'automatic': automatic}
        try:
            result = await self.request(ident, '/chat/completions', {
                'model': doc['model'], 'messages': [{'role': 'user', 'content': 'Connectivity check. Reply OK only.'}],
                'max_completion_tokens': 32, 'thinking': {'type': 'disabled'}, 'stream': False})
            choices = result.get('choices')
            usage = result.get('usage', {})
            if (not isinstance(choices, list) or len(choices) != 1 or not isinstance(choices[0], dict)
                    or choices[0].get('finish_reason') not in ('stop', 'length')
                    or not isinstance(choices[0].get('message'), dict)
                    or choices[0]['message'].get('tool_calls')
                    or not isinstance(usage, dict)
                    or any(type(usage.get(k)) is not int or usage[k] < 0 for k in ('prompt_tokens', 'completion_tokens'))):
                raise fail('SUPPORT_PROVIDER_INVALID', 502)
            health.update(state='reachable', code=None, input_tokens=usage['prompt_tokens'], output_tokens=usage['completion_tokens'])
        except Problem as exc:
            health['code'] = exc.code
        finally:
            health['latency_ms'] = round((time.monotonic() - started) * 1000)
            try:
                with self.store.transaction() as db:
                    doc['health'] = health
                    db.execute('UPDATE support_providers SET doc=? WHERE id=?', (dumps(doc), ident))
            finally:
                with self.store.lock:
                    self.busy.discard(ident)
        return health

    async def _loop(self):
        while not self.stopping.is_set():
            for doc in self.listing():
                if self.stopping.is_set():
                    return
                if doc['enabled'] and doc['auto_probe'] and doc['next_probe_at'] <= time.time():
                    try:
                        await self.probe(doc['id'], automatic=True)
                    except Problem:
                        pass  # expected disabled/busy/daily cap, not a false success
            try:
                await asyncio.wait_for(self.stopping.wait(), 5)
            except TimeoutError:
                pass

    def start(self):
        if self.enabled and self.task is None:
            with self.store.transaction() as db:
                for doc in self.listing():
                    if doc['health']['state'] == 'checking':
                        doc['health'] = {'state': 'failed', 'code': 'SUPPORT_PROBE_INTERRUPTED', 'checked_at': now()}
                        db.execute('UPDATE support_providers SET doc=? WHERE id=?', (dumps(doc), doc['id']))
            self.task = asyncio.create_task(self._loop(), name='support-provider-probes')

    async def close(self):
        self.stopping.set()
        if self.task is not None:
            self.task.cancel()
            try:
                await self.task
            except asyncio.CancelledError:
                pass
