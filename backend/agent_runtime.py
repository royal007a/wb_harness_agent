"""Isolated Provider → Model → Agent → Session/Exchange local chat runtime."""
from __future__ import annotations

import json
import os
import re
from collections.abc import AsyncIterator
from pathlib import Path
from urllib.parse import urlparse

from jsonschema import Draft202012Validator, FormatChecker

from .analysis import Problem, digest
from .provider_adapters import ProviderAdapterRegistry, ProviderRequest
from .store import dumps, now, uid


ROOT = Path(__file__).resolve().parents[1]
CONTRACT = json.loads((ROOT / 'specs/v1/agent-runtime.schema.json').read_text())
SENSITIVE_INPUT = re.compile(r'(?:\b(?:api[_ -]?key|client[_ -]?secret|access[_ -]?token|refresh[_ -]?token)\s*[:=]|\bsk-[A-Za-z0-9_-]{10,}|\bAKIA[0-9A-Z]{16}\b)', re.I)


def validate_contract(name, value):
    schema = {'$ref': '#/$defs/' + name, '$defs': CONTRACT['$defs']}
    errors = list(Draft202012Validator(schema, format_checker=FormatChecker()).iter_errors(value))
    if errors:
        raise Problem('VALIDATION_ERROR', '请求不满足 Agent Runtime 契约。', 422)


def reject_sensitive(value):
    if isinstance(value, str) and SENSITIVE_INPUT.search(value):
        raise Problem('SENSITIVE_INPUT_REJECTED', 'Agent Runtime 不接收或保存凭证样式内容。', 422)


def safe_base_url(value):
    parsed = urlparse(value)
    if parsed.scheme not in {'https', 'http'} or not parsed.hostname or parsed.username or parsed.password:
        raise Problem('VALIDATION_ERROR', 'base_url 必须是不含凭证的 HTTP(S) 地址。', 422)
    if parsed.scheme != 'https' and parsed.hostname not in {'localhost', '127.0.0.1', '::1'}:
        raise Problem('VALIDATION_ERROR', '非本地 Provider 只能使用 HTTPS 地址。', 422)
    if parsed.query or parsed.fragment:
        raise Problem('VALIDATION_ERROR', 'base_url 不允许 query 或 fragment。', 422)
    return value.rstrip('/')


class KeyringCredentialResolver:
    """Resolve only an opaque keychain reference at the final transport boundary."""

    def resolve(self, credential_ref):
        if not credential_ref:
            raise Problem('MODEL_CREDENTIAL_REFERENCE_MISSING', 'Provider 未配置 Keychain credential reference。', 409)
        # Import lazily.  Configuration and default-disabled runtime never touch
        # the operating-system credential backend.
        try:
            import keyring
            secret = keyring.get_password('harnessagent', credential_ref)
        except Exception as exc:  # keyring availability differs by host
            raise Problem('MODEL_CREDENTIAL_UNAVAILABLE', '无法从本机 Keychain 解析 Provider 凭证。', 503) from exc
        if not secret:
            raise Problem('MODEL_CREDENTIAL_UNAVAILABLE', 'Keychain credential reference 未找到可用凭证。', 503)
        return secret


class AgentRuntime:
    """Independent local state plane; it never reads Product Task/Run tables."""

    def __init__(self, store, adapter_registry=None, credential_resolver=None, runtime_enabled=None):
        self.store = store
        self.adapters = adapter_registry or ProviderAdapterRegistry()
        self.credentials = credential_resolver or KeyringCredentialResolver()
        self._runtime_enabled = runtime_enabled

    def runtime_enabled(self):
        return self._runtime_enabled if self._runtime_enabled is not None else os.getenv('HARNESS_AGENT_RUNTIME') == 'enabled'

    @staticmethod
    def _idempotency_key(key):
        if not isinstance(key, str) or not 1 <= len(key) <= 128:
            raise Problem('VALIDATION_ERROR', '必须提供 1–128 字符的 Idempotency-Key。', 422)

    def _idempotent(self, scope, key, body, action):
        self._idempotency_key(key)
        request_digest = digest(dumps(body).encode())
        with self.store.transaction() as db:
            old = db.execute('SELECT digest,response FROM idempotency WHERE scope=? AND key=?', (scope, key)).fetchone()
            if old:
                if old['digest'] != request_digest:
                    raise Problem('CONFLICT', '同一幂等键已用于不同请求。', 409)
                return json.loads(old['response'])
            result = action(db, request_digest)
            db.execute('INSERT INTO idempotency VALUES(?,?,?,?)', (scope, key, request_digest, dumps(result)))
            return result

    @staticmethod
    def _assert_unique(db, table, field, value):
        rows = db.execute(f'SELECT doc FROM {table}').fetchall()
        if any(json.loads(row['doc']).get(field, '').casefold() == value.casefold() for row in rows):
            raise Problem('CONFLICT', '名称已存在。', 409)

    def runtime_status(self):
        return {
            'mode': 'provider_agent_chat_runtime@1',
            'runtime_enabled': self.runtime_enabled(),
            'credential_resolution': 'deferred_to_keychain_at_transport_boundary',
            'model_calls': 0,
            'provider_calls': 0,
            'network_calls': 0,
            'tool_binding_count': 0,
            'note': '默认关闭外部模型调用；配置不等于已获运行授权。',
        }

    def providers(self):
        return {'items': self.store.runtime_listing('runtime_provider_profiles'), 'runtime': self.runtime_status()}

    def create_provider(self, body, key):
        validate_contract('provider_create_request', body)
        name = body['name'].strip()
        if not name:
            raise Problem('VALIDATION_ERROR', '名称不能为空。', 422)
        reject_sensitive(name)
        credential_ref = body.get('credential_ref')
        if credential_ref:
            reject_sensitive(credential_ref)
        normalized = {**body, 'name': name, 'base_url': safe_base_url(body['base_url']),
                      'credential_ref': credential_ref or None, 'enabled': body.get('enabled', True)}

        def create(db, _request_digest):
            self._assert_unique(db, 'runtime_provider_profiles', 'name', name)
            profile = {'id': uid('rtp'), **normalized, 'adapter_status': self.adapters.status_for(normalized['type']),
                       'created_at': now(), 'updated_at': now()}
            validate_contract('provider_profile', profile)
            db.execute('INSERT INTO runtime_provider_profiles VALUES(?,?)', (profile['id'], dumps(profile)))
            return profile
        return self._idempotent('agent-runtime:providers', key, normalized, create)

    def provider_readiness(self, provider_id):
        provider = self.store.runtime_get('runtime_provider_profiles', provider_id)
        if not provider['enabled']:
            state, detail = 'disabled', 'Provider Profile 已禁用。'
        elif provider['adapter_status'] != 'supported':
            state, detail = 'adapter_not_implemented', '该 Provider 类型尚未实现，不会自动改用其他协议。'
        elif not self.runtime_enabled():
            state, detail = 'blocked_by_runtime_gate', 'HARNESS_AGENT_RUNTIME 未启用；未进行网络健康检查。'
        elif not provider['credential_ref']:
            state, detail = 'credential_reference_missing', '请配置不含秘密值的 Keychain credential reference。'
        else:
            state, detail = 'ready_to_attempt', '运行时和配置门禁满足；真实连接仍需在请求时从 Keychain 解析凭证。'
        return {'provider_id': provider['id'], 'state': state, 'detail': detail,
                'network_calls': 0, 'checked_at': now()}

    def models(self):
        return {'items': self.store.runtime_listing('runtime_model_profiles'), 'runtime': self.runtime_status()}

    def create_model(self, body, key):
        validate_contract('model_create_request', body)
        display_name, model_id = body['display_name'].strip(), body['model_id'].strip()
        if not display_name or not model_id:
            raise Problem('VALIDATION_ERROR', '模型展示名和调用标识不能为空。', 422)
        reject_sensitive(display_name); reject_sensitive(model_id)
        normalized = {**body, 'display_name': display_name, 'model_id': model_id, 'enabled': body.get('enabled', True)}

        def create(db, _request_digest):
            provider = self.store.runtime_get('runtime_provider_profiles', normalized['provider_profile_id'])
            if not provider['enabled']:
                raise Problem('DEPENDENCY_DISABLED', '不能为禁用 Provider 创建模型。', 409)
            rows = db.execute('SELECT doc FROM runtime_model_profiles WHERE provider_profile_id=?', (provider['id'],)).fetchall()
            if any(json.loads(row['doc'])['model_id'] == model_id for row in rows):
                raise Problem('CONFLICT', '该 Provider 下模型调用标识已存在。', 409)
            profile = {'id': uid('rtm'), **normalized, 'created_at': now(), 'updated_at': now()}
            validate_contract('model_profile', profile)
            db.execute('INSERT INTO runtime_model_profiles VALUES(?,?,?)', (profile['id'], provider['id'], dumps(profile)))
            return profile
        return self._idempotent('agent-runtime:models', key, normalized, create)

    def agents(self):
        return {'items': self.store.runtime_listing('runtime_agent_profiles'), 'runtime': self.runtime_status()}

    def create_agent(self, body, key):
        validate_contract('agent_create_request', body)
        name, prompt = body['name'].strip(), body['system_prompt'].strip()
        if not name or not prompt:
            raise Problem('VALIDATION_ERROR', 'Agent 名称和 System Prompt 不能为空。', 422)
        for text in (name, body['description'], prompt):
            reject_sensitive(text)
        normalized = {**body, 'name': name, 'system_prompt': prompt, 'enabled': body.get('enabled', True)}

        def create(db, _request_digest):
            self._assert_unique(db, 'runtime_agent_profiles', 'name', name)
            model = self.store.runtime_get('runtime_model_profiles', normalized['model_profile_id'])
            provider = self.store.runtime_get('runtime_provider_profiles', model['provider_profile_id'])
            if not model['enabled'] or not provider['enabled']:
                raise Problem('DEPENDENCY_DISABLED', 'Agent 只能绑定启用的模型和 Provider。', 409)
            profile = {'id': uid('rta'), **normalized, 'tool_binding_count': 0, 'created_at': now(), 'updated_at': now()}
            validate_contract('agent_profile', profile)
            db.execute('INSERT INTO runtime_agent_profiles VALUES(?,?,?)', (profile['id'], model['id'], dumps(profile)))
            return profile
        return self._idempotent('agent-runtime:agents', key, normalized, create)

    def _active_stack(self, agent_profile_id):
        agent = self.store.runtime_get('runtime_agent_profiles', agent_profile_id)
        model = self.store.runtime_get('runtime_model_profiles', agent['model_profile_id'])
        provider = self.store.runtime_get('runtime_provider_profiles', model['provider_profile_id'])
        if not agent['enabled'] or not model['enabled'] or not provider['enabled']:
            raise Problem('DEPENDENCY_DISABLED', 'Agent、模型或 Provider 已禁用。', 409)
        return agent, model, provider

    def sessions(self):
        return {'items': self.store.runtime_listing('runtime_chat_sessions'), 'runtime': self.runtime_status()}

    def create_session(self, body, key):
        validate_contract('session_create_request', body)
        title = body.get('title', '').strip()
        if title:
            reject_sensitive(title)
        normalized = {'agent_profile_id': body['agent_profile_id'], 'title': title}

        def create(db, _request_digest):
            agent, _model, _provider = self._active_stack(normalized['agent_profile_id'])
            session = {'id': uid('rts'), 'agent_profile_id': agent['id'], 'title': normalized['title'] or '与 ' + agent['name'] + ' 的会话',
                       'status': 'active', 'created_at': now(), 'updated_at': now()}
            validate_contract('chat_session', session)
            db.execute('INSERT INTO runtime_chat_sessions VALUES(?,?,?)', (session['id'], agent['id'], dumps(session)))
            return session
        return self._idempotent('agent-runtime:sessions', key, normalized, create)

    def session_detail(self, session_id):
        session = self.store.runtime_get('runtime_chat_sessions', session_id)
        return {'session': session, 'messages': self.store.runtime_messages(session_id),
                'exchanges': self.store.runtime_exchanges(session_id), 'runtime': self.runtime_status()}

    def prepare_exchange(self, session_id, body, key):
        validate_contract('send_message_request', body)
        content = body['content'].strip()
        if not content:
            raise Problem('VALIDATION_ERROR', '消息不能为空。', 422)
        reject_sensitive(content); self._idempotency_key(key)
        request_digest = digest(dumps({'content': content}).encode())
        with self.store.transaction() as db:
            session = self.store.runtime_get('runtime_chat_sessions', session_id)
            if session['status'] != 'active':
                raise Problem('SESSION_ARCHIVED', '会话已归档，不能继续发送消息。', 409)
            agent, _model, _provider = self._active_stack(session['agent_profile_id'])
            old = self.store.runtime_exchange(session_id, key)
            if old:
                if old['request_digest'] != request_digest:
                    raise Problem('CONFLICT', '同一幂等键已用于不同消息。', 409)
                return old
            sequence = db.execute('SELECT COALESCE(MAX(sequence), 0) + 1 FROM runtime_chat_messages WHERE session_id=?', (session_id,)).fetchone()[0]
            user_message = {'id': uid('rtx'), 'session_id': session_id, 'sequence': sequence, 'role': 'user', 'content': content, 'created_at': now()}
            validate_contract('chat_message', user_message)
            db.execute('INSERT INTO runtime_chat_messages VALUES(?,?,?,?)', (user_message['id'], session_id, sequence, dumps(user_message)))
            context_count = min(sequence, agent['max_context_turns'] * 2)
            exchange = {'id': uid('rte'), 'session_id': session_id, 'idempotency_key': key, 'request_digest': request_digest,
                        'user_message_id': user_message['id'], 'assistant_message_id': None, 'status': 'queued', 'error_code': None,
                        'context_message_count': context_count, 'model_calls': 0, 'provider_calls': 0, 'created_at': now(), 'updated_at': now()}
            validate_contract('exchange', exchange)
            db.execute('INSERT INTO runtime_chat_exchanges VALUES(?,?,?,?,?)', (exchange['id'], session_id, key, request_digest, dumps(exchange)))
            session['updated_at'] = now()
            db.execute('UPDATE runtime_chat_sessions SET doc=? WHERE id=?', (dumps(session), session_id))
            return exchange

    def _save_exchange(self, db, exchange):
        exchange['updated_at'] = now()
        validate_contract('exchange', exchange)
        db.execute('UPDATE runtime_chat_exchanges SET doc=? WHERE id=?', (dumps(exchange), exchange['id']))

    def _context(self, session_id, max_turns):
        messages = self.store.runtime_messages(session_id)
        return messages[-(max_turns * 2):]

    def _failure(self, exchange_id, code):
        with self.store.transaction() as db:
            exchange = self.store.runtime_get('runtime_chat_exchanges', exchange_id)
            if exchange['status'] in {'queued', 'streaming'}:
                exchange['status'], exchange['error_code'] = 'failed', code
                self._save_exchange(db, exchange)
            return exchange

    def cancel_exchange(self, exchange_id):
        """Persist a terminal cancellation; never delete messages or exchange evidence."""
        with self.store.transaction() as db:
            exchange = self.store.runtime_get('runtime_chat_exchanges', exchange_id)
            if exchange['status'] in {'queued', 'streaming'}:
                exchange['status'], exchange['error_code'] = 'cancelled', None
                self._save_exchange(db, exchange)
            return exchange

    async def stream_exchange(self, exchange_id) -> AsyncIterator[dict]:
        exchange = self.store.runtime_get('runtime_chat_exchanges', exchange_id)
        if exchange['status'] == 'succeeded':
            message = self.store.runtime_get('runtime_chat_messages', exchange['assistant_message_id'])
            for chunk in self.chunk_text(message['content']):
                yield {'type': 'delta', 'exchange_id': exchange['id'], 'content': chunk, 'model_calls': exchange['model_calls'], 'provider_calls': exchange['provider_calls']}
            yield {'type': 'done', 'exchange_id': exchange['id'], 'message_id': message['id'], 'finish_reason': 'stop', 'model_calls': exchange['model_calls'], 'provider_calls': exchange['provider_calls']}
            return
        if exchange['status'] == 'failed':
            yield {'type': 'error', 'exchange_id': exchange['id'], 'error_code': exchange['error_code'], 'model_calls': 0, 'provider_calls': 0}
            return
        try:
            session = self.store.runtime_get('runtime_chat_sessions', exchange['session_id'])
            agent, model, provider = self._active_stack(session['agent_profile_id'])
            if not self.runtime_enabled():
                raise Problem('MODEL_RUNTIME_DISABLED', '模型运行时默认关闭；配置不等于外部数据发送授权。', 409)
            adapter = self.adapters.require(provider['type'])
            credential = self.credentials.resolve(provider['credential_ref'])
            context = self._context(session['id'], agent['max_context_turns'])
            with self.store.transaction() as db:
                current = self.store.runtime_get('runtime_chat_exchanges', exchange_id)
                if current['status'] == 'queued':
                    current['status'], current['model_calls'], current['provider_calls'] = 'streaming', 1, 1
                    self._save_exchange(db, current)
                exchange = current
            request = ProviderRequest(base_url=provider['base_url'], credential=credential, model_id=model['model_id'],
                                      system_prompt=agent['system_prompt'], messages=tuple({'role': item['role'], 'content': item['content']} for item in context),
                                      temperature=agent['temperature'], max_output_tokens=agent['max_output_tokens'])
            chunks = []
            async for chunk in adapter.stream(request):
                chunks.append(chunk)
                yield {'type': 'delta', 'exchange_id': exchange_id, 'content': chunk, 'model_calls': 1, 'provider_calls': 1}
            content = ''.join(chunks).strip()
            if not content:
                raise Problem('MODEL_EMPTY_RESPONSE', '模型 Provider 未返回可用文本。', 502)
            with self.store.transaction() as db:
                current = self.store.runtime_get('runtime_chat_exchanges', exchange_id)
                next_sequence = db.execute('SELECT COALESCE(MAX(sequence), 0) + 1 FROM runtime_chat_messages WHERE session_id=?', (session['id'],)).fetchone()[0]
                message = {'id': uid('rtx'), 'session_id': session['id'], 'sequence': next_sequence, 'role': 'assistant', 'content': content, 'created_at': now()}
                validate_contract('chat_message', message)
                db.execute('INSERT INTO runtime_chat_messages VALUES(?,?,?,?)', (message['id'], session['id'], next_sequence, dumps(message)))
                current['status'], current['assistant_message_id'], current['error_code'] = 'succeeded', message['id'], None
                self._save_exchange(db, current)
            yield {'type': 'done', 'exchange_id': exchange_id, 'message_id': message['id'], 'finish_reason': 'stop', 'model_calls': 1, 'provider_calls': 1}
        except Problem as exc:
            failed = self._failure(exchange_id, exc.code)
            yield {'type': 'error', 'exchange_id': failed['id'], 'error_code': exc.code, 'model_calls': failed['model_calls'], 'provider_calls': failed['provider_calls']}
        except Exception:
            failed = self._failure(exchange_id, 'MODEL_RUNTIME_INTERNAL_ERROR')
            yield {'type': 'error', 'exchange_id': failed['id'], 'error_code': 'MODEL_RUNTIME_INTERNAL_ERROR', 'model_calls': failed['model_calls'], 'provider_calls': failed['provider_calls']}

    @staticmethod
    def chunk_text(text):
        size = max(1, len(text) // 4)
        for offset in range(0, len(text), size):
            yield text[offset:offset + size]
