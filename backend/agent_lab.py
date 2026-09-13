"""Local, no-model Provider/Agent configuration and streaming chat demonstration."""
import json
import re
from pathlib import Path
from urllib.parse import urlparse

from jsonschema import Draft202012Validator, FormatChecker

from .analysis import Problem, digest
from .store import dumps, now, uid


ROOT = Path(__file__).resolve().parents[1]
CONTRACT = json.loads((ROOT / 'specs/v1/local-agent-lab.schema.json').read_text())
SENSITIVE_INPUT = re.compile(r'(?:\b(?:api[_ -]?key|client[_ -]?secret|access[_ -]?token|refresh[_ -]?token)\s*[:=]|\bsk-[A-Za-z0-9_-]{10,}|\bAKIA[0-9A-Z]{16}\b)', re.I)
LOCAL_DEMO_REPLY = '本地演示已完成：配置、会话、消息持久化与 POST SSE 流均已验证。当前没有调用模型、Provider、网络或工具，因此这不是模型对问题的实际回答。'


def validate_contract(name, value):
    schema = {'$ref': '#/$defs/' + name, '$defs': CONTRACT['$defs']}
    errors = list(Draft202012Validator(schema, format_checker=FormatChecker()).iter_errors(value))
    if errors:
        raise Problem('VALIDATION_ERROR', '请求不满足 Local Agent Lab 契约。', 422)


def reject_sensitive(value):
    if isinstance(value, str) and SENSITIVE_INPUT.search(value):
        raise Problem('SENSITIVE_INPUT_REJECTED', '本地 Agent Lab 不接收或保存凭证样式内容。', 422)


def safe_base_url(value):
    parsed = urlparse(value)
    if parsed.scheme not in {'https', 'http'} or not parsed.hostname or parsed.username or parsed.password:
        raise Problem('VALIDATION_ERROR', 'base_url 必须是不含凭证的 HTTP(S) 地址。', 422)
    if parsed.scheme != 'https' and parsed.hostname not in {'localhost', '127.0.0.1', '::1'}:
        raise Problem('VALIDATION_ERROR', '非本地 Provider Profile 只能使用 HTTPS 地址。', 422)
    if parsed.query or parsed.fragment:
        raise Problem('VALIDATION_ERROR', 'base_url 不允许 query 或 fragment。', 422)
    return value.rstrip('/')


class LocalAgentLab:
    """Owns a deliberately separate, zero-network configuration/chat demo data plane."""

    def __init__(self, store):
        self.store = store

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

    def providers(self):
        return {'items': self.store.agent_lab_listing('provider_profiles'), 'runtime': self.runtime_status()}

    def create_provider(self, body, key):
        validate_contract('provider_create_request', body)
        name = body['name'].strip()
        if not name:
            raise Problem('VALIDATION_ERROR', '名称不能为空。', 422)
        reject_sensitive(name)
        base_url = safe_base_url(body['base_url'])
        normalized = {**body, 'name': name, 'base_url': base_url, 'enabled': body.get('enabled', True)}

        def create(db, _request_digest):
            self._assert_unique(db, 'provider_profiles', 'name', name)
            profile = {'id': uid('ppr'), **normalized, 'created_at': now(), 'updated_at': now()}
            validate_contract('provider_profile', profile)
            db.execute('INSERT INTO provider_profiles VALUES(?,?)', (profile['id'], dumps(profile)))
            return profile
        return self._idempotent('agent-lab:providers', key, normalized, create)

    def models(self):
        return {'items': self.store.agent_lab_listing('model_profiles'), 'runtime': self.runtime_status()}

    def create_model(self, body, key):
        validate_contract('model_create_request', body)
        display_name, model_id = body['display_name'].strip(), body['model_id'].strip()
        if not display_name or not model_id:
            raise Problem('VALIDATION_ERROR', '模型展示名和调用标识不能为空。', 422)
        reject_sensitive(display_name)
        reject_sensitive(model_id)
        normalized = {**body, 'display_name': display_name, 'model_id': model_id, 'enabled': body.get('enabled', True)}

        def create(db, _request_digest):
            provider = self.store.agent_lab_get('provider_profiles', normalized['provider_profile_id'])
            if not provider['enabled']:
                raise Problem('DEPENDENCY_DISABLED', '不能为禁用的 Provider Profile 创建模型。', 409)
            rows = db.execute('SELECT doc FROM model_profiles WHERE provider_profile_id=?', (provider['id'],)).fetchall()
            if any(json.loads(row['doc'])['model_id'] == model_id for row in rows):
                raise Problem('CONFLICT', '该 Provider 下模型调用标识已存在。', 409)
            profile = {'id': uid('mdl'), **normalized, 'created_at': now(), 'updated_at': now()}
            validate_contract('model_profile', profile)
            db.execute('INSERT INTO model_profiles VALUES(?,?,?)', (profile['id'], provider['id'], dumps(profile)))
            return profile
        return self._idempotent('agent-lab:models', key, normalized, create)

    def agents(self):
        return {'items': self.store.agent_lab_listing('agent_profiles'), 'runtime': self.runtime_status()}

    def create_agent(self, body, key):
        validate_contract('agent_create_request', body)
        name = body['name'].strip()
        prompt = body['system_prompt'].strip()
        if not name or not prompt:
            raise Problem('VALIDATION_ERROR', 'Agent 名称和 System Prompt 不能为空。', 422)
        for text in (name, body['description'], prompt):
            reject_sensitive(text)
        normalized = {**body, 'name': name, 'system_prompt': prompt, 'enabled': body.get('enabled', True)}

        def create(db, _request_digest):
            self._assert_unique(db, 'agent_profiles', 'name', name)
            model = self.store.agent_lab_get('model_profiles', normalized['model_profile_id'])
            provider = self.store.agent_lab_get('provider_profiles', model['provider_profile_id'])
            if not model['enabled'] or not provider['enabled']:
                raise Problem('DEPENDENCY_DISABLED', 'Agent 只能绑定已启用的模型和 Provider Profile。', 409)
            profile = {
                'id': uid('agt'), **normalized, 'tool_binding_count': 0,
                'created_at': now(), 'updated_at': now(),
            }
            validate_contract('agent_profile', profile)
            db.execute('INSERT INTO agent_profiles VALUES(?,?,?)', (profile['id'], model['id'], dumps(profile)))
            return profile
        return self._idempotent('agent-lab:agents', key, normalized, create)

    def _active_agent(self, agent_profile_id):
        agent = self.store.agent_lab_get('agent_profiles', agent_profile_id)
        model = self.store.agent_lab_get('model_profiles', agent['model_profile_id'])
        provider = self.store.agent_lab_get('provider_profiles', model['provider_profile_id'])
        if not agent['enabled'] or not model['enabled'] or not provider['enabled']:
            raise Problem('DEPENDENCY_DISABLED', 'Agent、模型或 Provider Profile 已禁用。', 409)
        return agent

    def sessions(self):
        return {'items': self.store.agent_lab_listing('chat_sessions'), 'runtime': self.runtime_status()}

    def create_session(self, body, key):
        validate_contract('session_create_request', body)
        title = body.get('title', '').strip()
        if title:
            reject_sensitive(title)
        normalized = {'agent_profile_id': body['agent_profile_id'], 'title': title}

        def create(db, _request_digest):
            agent = self._active_agent(normalized['agent_profile_id'])
            session = {
                'id': uid('chs'), 'agent_profile_id': agent['id'],
                'title': normalized['title'] or '与 ' + agent['name'] + ' 的本地演示',
                'status': 'active', 'created_at': now(), 'updated_at': now(),
            }
            validate_contract('chat_session', session)
            db.execute('INSERT INTO chat_sessions VALUES(?,?,?)', (session['id'], agent['id'], dumps(session)))
            return session
        return self._idempotent('agent-lab:sessions', key, normalized, create)

    def session_detail(self, session_id):
        session = self.store.agent_lab_get('chat_sessions', session_id)
        return {'session': session, 'messages': self.store.chat_messages(session_id), 'runtime': self.runtime_status()}

    def send_message(self, session_id, body, key):
        validate_contract('send_message_request', body)
        content = body['content'].strip()
        if not content:
            raise Problem('VALIDATION_ERROR', '消息不能为空。', 422)
        reject_sensitive(content)
        normalized = {'content': content}
        self._idempotency_key(key)
        request_digest = digest(dumps(normalized).encode())
        with self.store.transaction() as db:
            session = self.store.agent_lab_get('chat_sessions', session_id)
            if session['status'] != 'active':
                raise Problem('SESSION_ARCHIVED', '会话已归档，不能继续发送消息。', 409)
            agent = self._active_agent(session['agent_profile_id'])
            old = self.store.chat_exchange(session_id, key)
            if old:
                if old['request_digest'] != request_digest:
                    raise Problem('CONFLICT', '同一幂等键已用于不同消息。', 409)
                return old
            next_sequence = db.execute('SELECT COALESCE(MAX(sequence), 0) + 1 FROM chat_messages WHERE session_id=?',
                                       (session_id,)).fetchone()[0]
            user_message = {
                'id': uid('chm'), 'session_id': session_id, 'sequence': next_sequence,
                'role': 'user', 'content': content, 'generation': 'user_input', 'created_at': now(),
            }
            assistant_message = {
                'id': uid('chm'), 'session_id': session_id, 'sequence': next_sequence + 1,
                'role': 'assistant', 'content': LOCAL_DEMO_REPLY, 'generation': 'local_demo', 'created_at': now(),
            }
            validate_contract('chat_message', user_message)
            validate_contract('chat_message', assistant_message)
            db.execute('INSERT INTO chat_messages VALUES(?,?,?,?)',
                       (user_message['id'], session_id, user_message['sequence'], dumps(user_message)))
            db.execute('INSERT INTO chat_messages VALUES(?,?,?,?)',
                       (assistant_message['id'], session_id, assistant_message['sequence'], dumps(assistant_message)))
            session['updated_at'] = now()
            db.execute('UPDATE chat_sessions SET doc=? WHERE id=?', (dumps(session), session_id))
            exchange = {
                'id': uid('che'), 'session_id': session_id, 'idempotency_key': key,
                'request_digest': request_digest, 'user_message_id': user_message['id'],
                'assistant_message_id': assistant_message['id'], 'assistant_content': LOCAL_DEMO_REPLY,
                'agent_profile_id': agent['id'], 'model_calls': 0, 'provider_calls': 0, 'created_at': now(),
            }
            db.execute('INSERT INTO chat_exchanges VALUES(?,?,?,?,?)',
                       (exchange['id'], session_id, key, request_digest, dumps(exchange)))
            return exchange

    @staticmethod
    def stream_chunks(exchange):
        text = exchange['assistant_content']
        # Three coarse chunks make the browser transport behavior visible without simulating a model token stream.
        size = max(1, len(text) // 3)
        for offset in range(0, len(text), size):
            yield text[offset:offset + size]

    @staticmethod
    def runtime_status():
        return {
            'mode': 'local_deterministic_demo',
            'model_calls': 0,
            'provider_calls': 0,
            'network_calls': 0,
            'tool_calls': 0,
            'tool_binding_count': 0,
            'note': '仅验证配置、会话和流式交互；真实模型未启用。',
        }
