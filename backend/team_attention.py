"""Metadata-only local Team attention, work-mark, lease and freshness control.

This module deliberately does not contain a message transport, message body,
Agent loop, Provider call, tool invocation or authenticated HTTP principal. It
is the durable protocol that a separately admitted runtime must obey later.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from jsonschema import Draft202012Validator, FormatChecker

from .analysis import Problem, digest
from .store import dumps, now, uid
from .team_foundation import TeamFoundation, is_list_visibility_denial
from .team_security import reject_sensitive


ROOT = Path(__file__).resolve().parents[1]
CONTRACT = json.loads((ROOT / 'specs/v1/team-attention.schema.json').read_text())
PRIORITY = {
    'human_correction': 100,
    'direct_mention': 80,
    'task_review': 60,
    'subscription_update': 40,
}


def validate_contract(name, value):
    schema = {'$ref': '#/$defs/' + name, '$defs': CONTRACT['$defs']}
    errors = list(Draft202012Validator(schema, format_checker=FormatChecker()).iter_errors(value))
    if errors:
        raise Problem('TEAM_ATTENTION_CONTRACT_INVALID', '请求不满足 Team Attention 契约。', 422)


def iso_now():
    return datetime.now(timezone.utc)


def parse_time(value):
    return datetime.fromisoformat(value.replace('Z', '+00:00'))


class TeamAttention:
    """SQLite attention state constrained by TeamFoundation access checks."""

    def __init__(self, store, foundation: TeamFoundation):
        self.store = store
        self.foundation = foundation

    @staticmethod
    def runtime_status():
        return {
            'mode': 'local_team_attention@1',
            'protocol_identity_authentication': 'not_connected',
            'agent_runtime': 'not_connected',
            'external_model_calls': 0,
            'external_tool_calls': 0,
            'message_delivery': 'manual_protocol_ingest_only',
            'automatic_dispatch': False,
            'note': ('只保存已授权 Channel 的 source_ref、sequence、read cursor、work mark 和 attention lease；'
                     '不保存消息正文或附件，不启动消息投递、Agent、模型、工具或自动审批。'),
        }

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
            result = action(db)
            db.execute('INSERT INTO idempotency VALUES(?,?,?,?)', (scope, key, request_digest, dumps(result)))
            return result

    @staticmethod
    def _row(db, table, where, params, code, message):
        row = db.execute('SELECT doc FROM ' + table + ' WHERE ' + where, params).fetchone()
        if not row:
            raise Problem(code, message, 404)
        return json.loads(row['doc'])

    def _item(self, db, item_id):
        return self._row(db, 'team_attention_items', 'id=?', (item_id,),
                         'TEAM_ATTENTION_NOT_FOUND', 'Attention item 不存在。')

    def _mark(self, db, item_id, agent_id):
        return self._row(db, 'team_attention_work_marks', 'item_id=? AND agent_id=?', (item_id, agent_id),
                         'TEAM_WORK_MARK_NOT_FOUND', 'Attention item 缺少 Work mark。')

    @staticmethod
    def _write_conversation(db, conversation):
        validate_contract('conversation', conversation)
        db.execute('INSERT INTO team_attention_conversations(channel_id,thread_id,doc) VALUES(?,?,?) '
                   'ON CONFLICT(channel_id,thread_id) DO UPDATE SET doc=excluded.doc',
                   (conversation['channel_id'], conversation['thread_id'], dumps(conversation)))

    @staticmethod
    def _write_cursor(db, cursor):
        validate_contract('read_cursor', cursor)
        db.execute('INSERT INTO team_attention_read_cursors(channel_id,thread_id,agent_id,doc) VALUES(?,?,?,?) '
                   'ON CONFLICT(channel_id,thread_id,agent_id) DO UPDATE SET doc=excluded.doc',
                   (cursor['channel_id'], cursor['thread_id'], cursor['agent_id'], dumps(cursor)))

    @staticmethod
    def _write_item(db, item):
        validate_contract('attention_item', item)
        db.execute('UPDATE team_attention_items SET doc=? WHERE id=?', (dumps(item), item['id']))

    @staticmethod
    def _write_mark(db, mark):
        validate_contract('work_mark', mark)
        db.execute('UPDATE team_attention_work_marks SET doc=? WHERE item_id=? AND agent_id=?',
                   (dumps(mark), mark['item_id'], mark['agent_id']))

    def _conversation(self, db, workspace_id, channel_id, thread_id, create=False):
        row = db.execute('SELECT doc FROM team_attention_conversations WHERE channel_id=? AND thread_id=?',
                         (channel_id, thread_id)).fetchone()
        if row:
            conversation = json.loads(row['doc'])
            if conversation['workspace_id'] != workspace_id:
                raise Problem('TEAM_ATTENTION_SCOPE_INVALID', 'Conversation Workspace 与 Channel 不一致。', 409)
            return conversation
        if not create:
            return None
        created_at = now()
        conversation = {
            'schema_version': 'team-conversation@1', 'workspace_id': workspace_id,
            'channel_id': channel_id, 'thread_id': thread_id, 'latest_sequence': 0,
            'created_at': created_at, 'updated_at': created_at,
        }
        self._write_conversation(db, conversation)
        return conversation

    @staticmethod
    def _cursor(db, channel_id, thread_id, agent_id):
        row = db.execute('SELECT doc FROM team_attention_read_cursors WHERE channel_id=? AND thread_id=? AND agent_id=?',
                         (channel_id, thread_id, agent_id)).fetchone()
        return json.loads(row['doc']) if row else None

    def _assert_target_access(self, db, item, actor_id):
        if item['target_agent_id'] != actor_id:
            raise Problem('TEAM_ATTENTION_TARGET_FORBIDDEN', '只能处理发送给当前 protocol identity 的 Attention item。', 403)
        workspace, channel, _, _ = self.foundation.assert_channel_access(db, item['channel_id'], actor_id)
        if workspace['id'] != item['workspace_id']:
            raise Problem('TEAM_ATTENTION_SCOPE_INVALID', 'Attention item Workspace 与 Channel 不一致。', 409)
        return workspace, channel

    @staticmethod
    def _touch_item(item):
        item['version'] += 1
        item['updated_at'] = now()

    @staticmethod
    def _touch_mark(mark, status):
        mark['status'] = status
        mark['updated_at'] = now()

    def _expire_item_lease(self, db, item):
        lease = item.get('lease')
        if lease and parse_time(lease['expires_at']) <= iso_now():
            db.execute('DELETE FROM team_attention_leases WHERE item_id=?', (item['id'],))
            item['lease'] = None
            if item['status'] == 'in_progress':
                item['status'] = 'pending'
                self._touch_item(item)
                self._write_item(db, item)
            mark = self._mark(db, item['id'], item['target_agent_id'])
            if mark['status'] != 'cleared':
                self._touch_mark(mark, 'open')
                self._write_mark(db, mark)
        return item

    def _expire_agent_lease(self, db, agent_id):
        row = db.execute('SELECT item_id FROM team_attention_leases WHERE agent_id=?', (agent_id,)).fetchone()
        if not row:
            return None
        item = self._item(db, row['item_id'])
        self._expire_item_lease(db, item)
        row = db.execute('SELECT item_id FROM team_attention_leases WHERE agent_id=?', (agent_id,)).fetchone()
        return row['item_id'] if row else None

    def _assert_item_claim(self, db, item, actor_id):
        self._assert_target_access(db, item, actor_id)
        item = self._expire_item_lease(db, item)
        lease = item.get('lease')
        if (item['status'] != 'in_progress' or not lease or lease['claimant_id'] != actor_id
                or parse_time(lease['expires_at']) <= iso_now()):
            raise Problem('TEAM_ATTENTION_CLAIM_REQUIRED', '只有持有有效 Attention lease 的目标 identity 可以执行此动作。', 409)
        return item

    def _assert_fresh_conversation(self, db, workspace_id, channel_id, thread_id, actor_id, proof):
        conversation = self._conversation(db, workspace_id, channel_id, thread_id, create=False)
        latest = conversation['latest_sequence'] if conversation else 0
        if latest == 0:
            return conversation
        if proof is None:
            raise Problem('TEAM_FRESHNESS_REQUIRED', '该 Thread 有未确认的更新；请先读取最新 sequence 后再写入。', 409)
        validate_contract('freshness_proof', proof)
        cursor = self._cursor(db, channel_id, thread_id, actor_id)
        if (cursor is None or proof['read_sequence'] != latest
                or cursor['read_sequence'] != latest):
            raise Problem('TEAM_FRESHNESS_REQUIRED', 'Thread 已更新或 read cursor 过期；请补读后重新决定。', 409)
        return conversation

    def assert_task_freshness(self, db, task, actor_id, proof):
        """Called by TeamCoordination inside its existing write transaction."""
        thread_id = task.get('thread_id')
        if thread_id is None:
            return None
        return self._assert_fresh_conversation(
            db, task['workspace_id'], task['channel_id'], thread_id, actor_id, proof)

    def create_item(self, body, key):
        validate_contract('attention_item_create_request', body)
        reject_sensitive(body)

        def create(db):
            workspace, channel, _, _ = self.foundation.assert_channel_access(db, body['channel_id'], body['actor_id'])
            if workspace['id'] != body['workspace_id']:
                raise Problem('TEAM_ATTENTION_SCOPE_INVALID', 'Attention Workspace 必须与 Channel 所属 Workspace 一致。', 409)
            author = self.foundation._agent(db, body['actor_id'])
            self.foundation.assert_channel_access(db, body['channel_id'], body['target_agent_id'])
            if body['kind'] == 'human_correction' and author['kind'] != 'human':
                raise Problem('TEAM_ATTENTION_HUMAN_SOURCE_REQUIRED', 'human_correction 只能由 human protocol identity 登记。', 403)
            conversation = self._conversation(db, workspace['id'], channel['id'], body['thread_id'], create=True)
            conversation['latest_sequence'] += 1
            conversation['updated_at'] = now()
            self._write_conversation(db, conversation)
            created_at = now()
            item = {
                'schema_version': 'team-attention-item@1', 'id': uid('attention'),
                'workspace_id': workspace['id'], 'channel_id': channel['id'], 'thread_id': body['thread_id'],
                'source_ref': body['source_ref'], 'author_id': body['actor_id'],
                'target_agent_id': body['target_agent_id'], 'kind': body['kind'],
                'priority': PRIORITY[body['kind']], 'sequence': conversation['latest_sequence'],
                'status': 'pending', 'version': 1, 'lease': None,
                'created_at': created_at, 'updated_at': created_at,
            }
            mark = {
                'schema_version': 'team-work-mark@1', 'id': uid('workmark'), 'item_id': item['id'],
                'agent_id': item['target_agent_id'], 'status': 'open',
                'created_at': created_at, 'updated_at': created_at,
            }
            validate_contract('attention_item', item)
            validate_contract('work_mark', mark)
            db.execute('INSERT INTO team_attention_items(id,channel_id,thread_id,target_agent_id,doc) VALUES(?,?,?,?,?)',
                       (item['id'], item['channel_id'], item['thread_id'], item['target_agent_id'], dumps(item)))
            db.execute('INSERT INTO team_attention_work_marks(item_id,agent_id,doc) VALUES(?,?,?)',
                       (mark['item_id'], mark['agent_id'], dumps(mark)))
            return {'item': item, 'work_mark': mark, 'conversation': conversation}
        return self._idempotent('team-attention:item:create', key, body, create)

    def inbox(self, actor_id):
        with self.store.transaction() as db:
            self.foundation._agent(db, actor_id)
            self._expire_agent_lease(db, actor_id)
            rows = db.execute('SELECT doc FROM team_attention_items WHERE target_agent_id=? ORDER BY rowid',
                              (actor_id,)).fetchall()
            items = []
            for row in rows:
                item = self._expire_item_lease(db, json.loads(row['doc']))
                try:
                    self._assert_target_access(db, item, actor_id)
                except Problem as exc:
                    if not is_list_visibility_denial(exc):
                        raise
                    continue
                mark = self._mark(db, item['id'], actor_id)
                conversation = self._conversation(db, item['workspace_id'], item['channel_id'], item['thread_id'])
                cursor = self._cursor(db, item['channel_id'], item['thread_id'], actor_id)
                items.append({
                    'item': item, 'work_mark': mark,
                    'read_sequence': cursor['read_sequence'] if cursor else 0,
                    'latest_sequence': conversation['latest_sequence'] if conversation else 0,
                })
            items.sort(key=lambda value: (-value['item']['priority'], value['item']['sequence'], value['item']['id']))
            result = {'items': items, 'runtime': self.runtime_status()}
            validate_contract('inbox_list', result)
            return result

    def read_cursor(self, channel_id, thread_id, body, key):
        validate_contract('read_cursor_update_request', body)
        reject_sensitive(body)
        request = {**body, 'channel_id': channel_id, 'thread_id': thread_id}

        def update(db):
            workspace, channel, _, _ = self.foundation.assert_channel_access(db, channel_id, body['actor_id'])
            conversation = self._conversation(db, workspace['id'], channel['id'], thread_id, create=True)
            if body['expected_latest_sequence'] != conversation['latest_sequence']:
                raise Problem('TEAM_READ_SEQUENCE_STALE', '当前 Thread sequence 已变化；请重新读取后更新 cursor。', 409)
            cursor = {
                'schema_version': 'team-read-cursor@1', 'workspace_id': workspace['id'],
                'channel_id': channel['id'], 'thread_id': thread_id, 'agent_id': body['actor_id'],
                'read_sequence': conversation['latest_sequence'], 'updated_at': now(),
            }
            self._write_cursor(db, cursor)
            return {'cursor': cursor, 'conversation': conversation}
        return self._idempotent('team-attention:' + channel_id + ':' + thread_id + ':read', key, request, update)

    def claim(self, item_id, body, key):
        validate_contract('attention_claim_request', body)
        reject_sensitive(body)

        def claim(db):
            item = self._expire_item_lease(db, self._item(db, item_id))
            self._assert_target_access(db, item, body['actor_id'])
            existing = self._expire_agent_lease(db, body['actor_id'])
            if existing and existing != item_id:
                raise Problem('TEAM_ATTENTION_LEASE_CONFLICT', '同一 protocol identity 已领取另一件 Attention work。', 409)
            if item['status'] != 'pending' or item['lease'] is not None:
                raise Problem('TEAM_ATTENTION_CLAIM_CONFLICT', '该 Attention item 已被领取或已结束。', 409)
            expires_at = (iso_now() + timedelta(seconds=body['lease_seconds'])).isoformat().replace('+00:00', 'Z')
            lease = {'id': uid('attentionlease'), 'claimant_id': body['actor_id'], 'expires_at': expires_at}
            item['status'], item['lease'] = 'in_progress', lease
            self._touch_item(item)
            self._write_item(db, item)
            mark = self._mark(db, item_id, body['actor_id'])
            self._touch_mark(mark, 'in_progress')
            self._write_mark(db, mark)
            db.execute('INSERT INTO team_attention_leases(id,item_id,agent_id,doc) VALUES(?,?,?,?)',
                       (lease['id'], item_id, body['actor_id'], dumps(lease)))
            conversation = self._conversation(db, item['workspace_id'], item['channel_id'], item['thread_id'])
            return {'item': item, 'work_mark': mark, 'conversation': conversation}
        return self._idempotent('team-attention:' + item_id + ':claim', key, body, claim)

    def release(self, item_id, body, key):
        validate_contract('attention_release_request', body)
        reject_sensitive(body)

        def release(db):
            item = self._assert_item_claim(db, self._item(db, item_id), body['actor_id'])
            if item['version'] != body['expected_item_version']:
                raise Problem('TEAM_ATTENTION_VERSION_CONFLICT', 'Attention item 已变化；请重新读取后再写入。', 409)
            db.execute('DELETE FROM team_attention_leases WHERE item_id=?', (item_id,))
            item['status'], item['lease'] = 'pending', None
            self._touch_item(item)
            self._write_item(db, item)
            mark = self._mark(db, item_id, body['actor_id'])
            self._touch_mark(mark, 'open')
            self._write_mark(db, mark)
            conversation = self._conversation(db, item['workspace_id'], item['channel_id'], item['thread_id'])
            return {'item': item, 'work_mark': mark, 'conversation': conversation}
        return self._idempotent('team-attention:' + item_id + ':release', key, body, release)

    def complete(self, item_id, body, key):
        validate_contract('attention_complete_request', body)
        reject_sensitive(body)

        def complete(db):
            item = self._assert_item_claim(db, self._item(db, item_id), body['actor_id'])
            if item['version'] != body['expected_item_version']:
                raise Problem('TEAM_ATTENTION_VERSION_CONFLICT', 'Attention item 已变化；请重新读取后再写入。', 409)
            conversation = self._assert_fresh_conversation(
                db, item['workspace_id'], item['channel_id'], item['thread_id'], body['actor_id'], body['freshness'])
            db.execute('DELETE FROM team_attention_leases WHERE item_id=?', (item_id,))
            item['status'], item['lease'] = 'completed', None
            self._touch_item(item)
            self._write_item(db, item)
            mark = self._mark(db, item_id, body['actor_id'])
            self._touch_mark(mark, 'cleared')
            self._write_mark(db, mark)
            return {'item': item, 'work_mark': mark, 'conversation': conversation}
        return self._idempotent('team-attention:' + item_id + ':complete', key, body, complete)
