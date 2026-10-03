"""Metadata-only Team Session continuity and bounded handoff snapshots.

This is deliberately separate from Agent Lab/Runtime chat sessions.  It stores
no message body, prompt, model context, provider session, working directory,
credential, tool result or runtime telemetry.  The snapshot is a navigation
record made from existing Team Task and Attention protocol metadata; it never
changes those source objects or their freshness rules.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from jsonschema import Draft202012Validator, FormatChecker

from .analysis import Problem, digest
from .store import dumps, now, uid
from .team_foundation import TeamFoundation, is_list_visibility_denial
from .team_security import reject_sensitive


ROOT = Path(__file__).resolve().parents[1]
CONTRACT = json.loads((ROOT / 'specs/v1/team-session-continuity.schema.json').read_text())
OPEN_TASK_STATES = {'in_progress', 'in_review'}
TASK_LIMIT = 32
ATTENTION_LIMIT = 64
THREAD_LIMIT = 64


def validate_contract(name, value):
    schema = {'$ref': '#/$defs/' + name, '$defs': CONTRACT['$defs']}
    errors = list(Draft202012Validator(schema, format_checker=FormatChecker()).iter_errors(value))
    if errors:
        raise Problem('TEAM_SESSION_CONTRACT_INVALID', '请求不满足 Team Session Continuity 契约。', 422)


def iso_now():
    return datetime.now(timezone.utc)


def parse_time(value):
    return datetime.fromisoformat(value.replace('Z', '+00:00'))


class TeamSessionContinuity:
    """Durable protocol sessions with server-derived, metadata-only snapshots."""

    def __init__(self, store, foundation: TeamFoundation):
        self.store = store
        self.foundation = foundation

    @staticmethod
    def runtime_status():
        return {
            'mode': 'local_team_session_continuity@1',
            'protocol_identity_authentication': 'not_connected',
            'agent_runtime': 'not_connected',
            'runtime_telemetry': 'not_connected',
            'external_model_calls': 0,
            'external_tool_calls': 0,
            'automatic_rotation': False,
            'message_history': False,
            'note': ('只保存已授权 Channel 的 Session lifecycle 和由 Task/Attention 元数据生成的有界 Snapshot；'
                     '不保存/压缩消息或模型上下文，不连接 Runtime、Provider、工具、自动换代或自动恢复。'),
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

    def _session(self, db, session_id):
        return self._row(db, 'team_sessions', 'id=?', (session_id,),
                         'TEAM_SESSION_NOT_FOUND', 'Team Session 不存在。')

    def _handoff(self, db, handoff_id):
        return self._row(db, 'team_session_handoffs', 'id=?', (handoff_id,),
                         'TEAM_SESSION_HANDOFF_NOT_FOUND', 'Session Handoff 不存在。')

    @staticmethod
    def _write_session(db, session):
        validate_contract('team_session', session)
        db.execute('UPDATE team_sessions SET doc=? WHERE id=?', (dumps(session), session['id']))

    @staticmethod
    def _write_handoff(db, handoff):
        validate_contract('session_handoff', handoff)
        db.execute('UPDATE team_session_handoffs SET doc=?, consumed_by_session_id=? WHERE id=?',
                   (dumps(handoff), handoff['consumed_by_session_id'], handoff['id']))

    def _assert_session_access(self, db, session, actor_id):
        if session['agent_id'] != actor_id:
            raise Problem('TEAM_SESSION_OWNER_FORBIDDEN', '只能读取或换代属于当前 protocol identity 的 Team Session。', 403)
        workspace, channel, membership, channel_membership = self.foundation.assert_channel_access(
            db, session['channel_id'], actor_id)
        if workspace['id'] != session['workspace_id']:
            raise Problem('TEAM_SESSION_SCOPE_INVALID', 'Team Session Workspace 与 Channel 不一致。', 409)
        return workspace, channel, membership, channel_membership

    @staticmethod
    def _task_reference(task):
        return {
            'task_id': task['id'], 'task_version': task['version'],
            'status': task['status'], 'thread_id': task['thread_id'],
        }

    @staticmethod
    def _slice(values, limit):
        return values[:limit], max(len(values) - limit, 0)

    def _active_session(self, db, channel_id, agent_id):
        rows = db.execute('SELECT doc FROM team_sessions WHERE channel_id=? AND agent_id=? ORDER BY rowid',
                          (channel_id, agent_id)).fetchall()
        active = [json.loads(row['doc']) for row in rows if json.loads(row['doc'])['status'] == 'active']
        if len(active) > 1:
            raise Problem('TEAM_SESSION_STATE_CORRUPT', '同一 identity/Channel 存在多个 active Team Session。', 409)
        return active[0] if active else None

    @staticmethod
    def _valid_claim(task, agent_id):
        lease = task.get('lease')
        return (task['status'] == 'in_progress' and task.get('assignee_id') == agent_id and lease is not None
                and lease.get('claimant_id') == agent_id and parse_time(lease['expires_at']) > iso_now())

    def _snapshot(self, db, session):
        """Build a strict, bounded view without importing any free-text content."""
        _, _, _, channel_membership = self._assert_session_access(db, session, session['agent_id'])
        # Team Task v2 keeps its Workspace/Channel scope inside the versioned
        # document.  The legacy table deliberately has no denormalized
        # ``channel_id`` column, so filter only after decoding the document.
        # Do not add an unvalidated SQL predicate here: an upgrade must keep
        # legacy Task rows readable and, crucially, never widen the snapshot
        # beyond the explicit v2 scope check below.
        rows = db.execute('SELECT doc FROM team_tasks ORDER BY rowid').fetchall()
        tasks = []
        for row in rows:
            task = json.loads(row['doc'])
            if task.get('schema_version') != 'team-task@2' or task.get('workspace_id') != session['workspace_id']:
                continue
            try:
                self.foundation.assert_task_access(db, task, session['agent_id'])
            except Problem as exc:
                if not is_list_visibility_denial(exc, allow_legacy_task=True):
                    raise
                continue
            tasks.append(task)
        tasks.sort(key=lambda task: task['id'])
        owned_all = [self._task_reference(task) for task in tasks
                     if task.get('assignee_id') == session['agent_id'] and task['status'] in OPEN_TASK_STATES]
        review_all = [self._task_reference(task) for task in tasks
                      if task['status'] == 'in_review' and task['gate']['reviewer_id'] == session['agent_id']]
        can_claim = bool(set(channel_membership['roles']).intersection({'contributor', 'coordinator'}))
        available_all = [self._task_reference(task) for task in tasks
                         if can_claim and task['status'] == 'todo' and task.get('assignee_id') is None]
        active_claims = [self._task_reference(task) for task in tasks if self._valid_claim(task, session['agent_id'])]
        current_task = active_claims[0] if len(active_claims) == 1 else None
        owned_tasks, omitted_owned = self._slice(owned_all, TASK_LIMIT)
        pending_reviews, omitted_reviews = self._slice(review_all, TASK_LIMIT)
        available_tasks, omitted_available = self._slice(available_all, TASK_LIMIT)

        attention_rows = db.execute(
            'SELECT doc FROM team_attention_items WHERE channel_id=? AND target_agent_id=? ORDER BY rowid',
            (session['channel_id'], session['agent_id'])).fetchall()
        attention_all = []
        for row in attention_rows:
            item = json.loads(row['doc'])
            if item.get('workspace_id') != session['workspace_id']:
                continue
            mark_row = db.execute('SELECT doc FROM team_attention_work_marks WHERE item_id=? AND agent_id=?',
                                  (item['id'], session['agent_id'])).fetchone()
            if not mark_row:
                continue
            mark = json.loads(mark_row['doc'])
            if mark['status'] == 'cleared':
                continue
            attention_all.append({
                'item_id': item['id'], 'thread_id': item['thread_id'], 'sequence': item['sequence'],
                'status': item['status'], 'version': item['version'], 'work_mark_status': mark['status'],
            })
        attention_all.sort(key=lambda item: (item['thread_id'], item['sequence'], item['item_id']))
        attention_items, omitted_attention = self._slice(attention_all, ATTENTION_LIMIT)

        thread_ids = sorted({reference['thread_id'] for reference in owned_all + review_all + available_all
                             if reference['thread_id'] is not None} | {item['thread_id'] for item in attention_all})
        thread_all = []
        for thread_id in thread_ids:
            conversation_row = db.execute(
                'SELECT doc FROM team_attention_conversations WHERE channel_id=? AND thread_id=?',
                (session['channel_id'], thread_id)).fetchone()
            cursor_row = db.execute(
                'SELECT doc FROM team_attention_read_cursors WHERE channel_id=? AND thread_id=? AND agent_id=?',
                (session['channel_id'], thread_id, session['agent_id'])).fetchone()
            conversation = json.loads(conversation_row['doc']) if conversation_row else None
            cursor = json.loads(cursor_row['doc']) if cursor_row else None
            thread_all.append({
                'thread_id': thread_id,
                'latest_sequence': conversation['latest_sequence'] if conversation else 0,
                'read_sequence': cursor['read_sequence'] if cursor else 0,
            })
        thread_freshness, omitted_threads = self._slice(thread_all, THREAD_LIMIT)
        snapshot = {
            'schema_version': 'session-continuity-snapshot@1',
            'workspace_id': session['workspace_id'], 'channel_id': session['channel_id'],
            'agent_id': session['agent_id'], 'current_task': current_task,
            'owned_tasks': owned_tasks, 'pending_reviews': pending_reviews, 'available_tasks': available_tasks,
            'attention_items': attention_items, 'thread_freshness': thread_freshness,
            'omitted_counts': {
                'owned_tasks': omitted_owned, 'pending_reviews': omitted_reviews,
                'available_tasks': omitted_available, 'attention_items': omitted_attention,
                'thread_freshness': omitted_threads,
            },
            'generated_at': now(),
        }
        validate_contract('continuity_snapshot', snapshot)
        return snapshot

    def sessions(self, actor_id, channel_id=None):
        with self.store.transaction() as db:
            self.foundation._agent(db, actor_id)
            if channel_id is not None:
                self.foundation.assert_channel_access(db, channel_id, actor_id)
            query = 'SELECT doc FROM team_sessions WHERE agent_id=?'
            params = [actor_id]
            if channel_id is not None:
                query += ' AND channel_id=?'
                params.append(channel_id)
            rows = db.execute(query + ' ORDER BY rowid DESC', tuple(params)).fetchall()
            items = []
            for row in rows:
                session = json.loads(row['doc'])
                try:
                    self._assert_session_access(db, session, actor_id)
                except Problem as exc:
                    if not is_list_visibility_denial(exc):
                        raise
                    continue
                items.append(session)
            result = {'items': items, 'runtime': self.runtime_status()}
            validate_contract('session_list', result)
            return result

    def create_session(self, body, key):
        validate_contract('session_create_request', body)
        reject_sensitive(body)

        def create(db):
            workspace, channel, _, _ = self.foundation.assert_channel_access(db, body['channel_id'], body['actor_id'])
            if workspace['id'] != body['workspace_id']:
                raise Problem('TEAM_SESSION_SCOPE_INVALID', 'Session Workspace 必须与 Channel 所属 Workspace 一致。', 409)
            if self._active_session(db, channel['id'], body['actor_id']) is not None:
                raise Problem('TEAM_SESSION_ACTIVE_CONFLICT', '同一 identity 在此 Channel 已有 active Team Session。', 409)
            inherited = None
            inherited_id = body.get('inherited_handoff_id')
            if inherited_id is not None:
                inherited = self._handoff(db, inherited_id)
                if (inherited['workspace_id'] != workspace['id'] or inherited['channel_id'] != channel['id']
                        or inherited['agent_id'] != body['actor_id']):
                    raise Problem('TEAM_SESSION_HANDOFF_SCOPE_FORBIDDEN', '只能继承同 Workspace/Channel/identity 的 Session Handoff。', 403)
                if inherited['consumed_by_session_id'] is not None:
                    raise Problem('TEAM_SESSION_HANDOFF_CONSUMED', '该 Session Handoff 已被消费。', 409)
                predecessor = self._session(db, inherited['session_id'])
                if predecessor['status'] != 'retired':
                    raise Problem('TEAM_SESSION_HANDOFF_STATE_INVALID', '只有 retired Session 的 Handoff 可以创建 successor。', 409)
            created_at = now()
            session = {
                'schema_version': 'team-session@1', 'id': uid('teamsession'),
                'workspace_id': workspace['id'], 'channel_id': channel['id'], 'agent_id': body['actor_id'],
                'status': 'active', 'version': 1, 'inherited_handoff_id': inherited_id,
                'created_at': created_at, 'updated_at': created_at, 'retired_at': None,
            }
            validate_contract('team_session', session)
            db.execute('INSERT INTO team_sessions(id,channel_id,agent_id,doc) VALUES(?,?,?,?)',
                       (session['id'], session['channel_id'], session['agent_id'], dumps(session)))
            if inherited is not None:
                inherited['consumed_by_session_id'] = session['id']
                inherited['updated_at'] = now()
                self._write_handoff(db, inherited)
            continuity = self._snapshot(db, session)
            result = {'session': session, 'continuity': continuity, 'inherited_handoff': inherited}
            validate_contract('session_create_result', result)
            return result
        return self._idempotent('team-session:create', key, body, create)

    def detail(self, session_id, actor_id):
        with self.store.transaction() as db:
            session = self._session(db, session_id)
            self._assert_session_access(db, session, actor_id)
            inherited = self._handoff(db, session['inherited_handoff_id']) if session['inherited_handoff_id'] else None
            if inherited is not None and (inherited['agent_id'] != actor_id or inherited['channel_id'] != session['channel_id']):
                raise Problem('TEAM_SESSION_HANDOFF_SCOPE_FORBIDDEN', 'Session Handoff 不属于当前 identity/Channel。', 403)
            result = {
                'session': session, 'continuity': self._snapshot(db, session),
                'inherited_handoff': inherited, 'runtime': self.runtime_status(),
            }
            validate_contract('session_detail', result)
            return result

    def handoff(self, session_id, body, key):
        validate_contract('session_handoff_create_request', body)
        reject_sensitive(body)

        def handoff(db):
            session = self._session(db, session_id)
            self._assert_session_access(db, session, body['actor_id'])
            if session['status'] != 'active':
                raise Problem('TEAM_SESSION_STATE_INVALID', '只有 active Team Session 可以创建 Handoff。', 409)
            if session['version'] != body['expected_session_version']:
                raise Problem('TEAM_SESSION_VERSION_CONFLICT', 'Team Session 已变化；请重新读取后再换代。', 409)
            continuity = self._snapshot(db, session)
            created_at = now()
            handoff_record = {
                'schema_version': 'team-session-handoff@1', 'id': uid('sessionhandoff'),
                'session_id': session['id'], 'workspace_id': session['workspace_id'],
                'channel_id': session['channel_id'], 'agent_id': session['agent_id'],
                'reason': body['reason'], 'snapshot': continuity, 'consumed_by_session_id': None,
                'created_at': created_at, 'updated_at': created_at,
            }
            validate_contract('session_handoff', handoff_record)
            db.execute('INSERT INTO team_session_handoffs(id,session_id,channel_id,agent_id,consumed_by_session_id,doc) VALUES(?,?,?,?,?,?)',
                       (handoff_record['id'], session['id'], session['channel_id'], session['agent_id'], None,
                        dumps(handoff_record)))
            session['status'] = 'retired'
            session['version'] += 1
            session['retired_at'] = now()
            session['updated_at'] = session['retired_at']
            self._write_session(db, session)
            result = {'session': session, 'handoff': handoff_record, 'continuity': continuity}
            validate_contract('session_handoff_result', result)
            return result
        return self._idempotent('team-session:' + session_id + ':handoff', key, body, handoff)
