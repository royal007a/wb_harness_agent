"""Local, deterministic Team Task / Handoff / Gate control-plane slice.

This module deliberately does not start Agents, invoke models, or grant tool
permissions.  It persists the collaboration protocol that later runtimes must
obey, while keeping it separate from the fixed CSV Product Task/Run contract.
"""
from __future__ import annotations

import json
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

from jsonschema import Draft202012Validator, FormatChecker

from .analysis import Problem, digest
from .store import dumps, now, uid


ROOT = Path(__file__).resolve().parents[1]
CONTRACT = json.loads((ROOT / 'specs/v1/team-coordination.schema.json').read_text())
TERMINAL = {'done', 'closed'}
SENSITIVE_INPUT = re.compile(
    r'(?:\b(?:api[_ -]?key|client[_ -]?secret|access[_ -]?token|refresh[_ -]?token|password)\s*[:=]'
    r'|\bsk-[A-Za-z0-9_-]{10,}|\bAKIA[0-9A-Z]{16}\b)', re.I)


def validate_contract(name, value):
    schema = {'$ref': '#/$defs/' + name, '$defs': CONTRACT['$defs']}
    errors = list(Draft202012Validator(schema, format_checker=FormatChecker()).iter_errors(value))
    if errors:
        raise Problem('VALIDATION_ERROR', '请求不满足 Team Coordination 契约。', 422)


def iso_now():
    return datetime.now(timezone.utc)


def parse_time(value):
    return datetime.fromisoformat(value.replace('Z', '+00:00'))


def reject_sensitive(value):
    """Keep collaboration metadata out of the local secret store by default."""
    if isinstance(value, str):
        if SENSITIVE_INPUT.search(value):
            raise Problem('SENSITIVE_INPUT_REJECTED', 'Team 协作记录不接收或保存凭证样式内容。', 422)
    elif isinstance(value, list):
        for item in value:
            reject_sensitive(item)
    elif isinstance(value, dict):
        for item in value.values():
            reject_sensitive(item)


class TeamCoordination:
    """One-process, local-admin Team Task state machine with auditable writes."""

    def __init__(self, store):
        self.store = store

    @staticmethod
    def runtime_status():
        return {
            'mode': 'local_team_coordination@1',
            'agent_runtime': 'not_connected',
            'external_model_calls': 0,
            'external_tool_calls': 0,
            'note': '只持久化 Task/Handoff/Gate；不启动 Agent、模型、外部工具或自动审批。',
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
    def _row_task(db, task_id):
        row = db.execute('SELECT doc FROM team_tasks WHERE id=?', (task_id,)).fetchone()
        if not row:
            raise Problem('TEAM_TASK_NOT_FOUND', 'Team Task 不存在。', 404)
        return json.loads(row['doc'])

    @staticmethod
    def _write_task(db, task):
        validate_contract('team_task', task)
        db.execute('UPDATE team_tasks SET doc=?, parent_task_id=? WHERE id=?',
                   (dumps(task), task['parent_task_id'], task['id']))

    @staticmethod
    def _touch(task):
        task['version'] += 1
        task['updated_at'] = now()

    def _expire_lease(self, db, task):
        lease = task.get('lease')
        if lease and parse_time(lease['expires_at']) <= iso_now():
            # An expired execution lease cannot silently keep a worker owner.
            # A rejected task retains its assignee but has no lease; that actor
            # must claim again before more mutations are permitted.
            task['status'] = 'todo'
            task['assignee_id'] = None
            task['lease'] = None
            self._touch(task)
            self._write_task(db, task)
        return task

    @staticmethod
    def _assert_version(task, expected):
        if task['version'] != expected:
            raise Problem('TEAM_TASK_VERSION_CONFLICT', 'Task 已变化；请重新读取后再写入。', 409)

    @staticmethod
    def _assert_active_claim(task, actor_id):
        lease = task.get('lease')
        if (task['status'] != 'in_progress' or task.get('assignee_id') != actor_id or not lease
                or lease['claimant_id'] != actor_id or parse_time(lease['expires_at']) <= iso_now()):
            raise Problem('TEAM_TASK_CLAIM_REQUIRED', '只有持有有效执行租约的负责人可以交接或提交。', 409)

    @staticmethod
    def _open_children(db, task_id):
        rows = db.execute('SELECT doc FROM team_tasks WHERE parent_task_id=?', (task_id,)).fetchall()
        return [json.loads(row['doc']) for row in rows if json.loads(row['doc'])['status'] not in TERMINAL]

    def create_task(self, body, key):
        validate_contract('team_task_create_request', body)
        reject_sensitive(body)

        def create(db):
            parent_id = body['parent_task_id']
            if parent_id:
                parent = self._row_task(db, parent_id)
                if parent['status'] in TERMINAL:
                    raise Problem('TEAM_TASK_PARENT_TERMINAL', '不能向已结束的父 Task 新增 Child。', 409)
                if parent['channel_id'] != body['channel_id']:
                    raise Problem('TEAM_TASK_PARENT_SCOPE_INVALID', 'Child Task 必须属于与父项相同的 Channel。', 409)
            created_at = now()
            task = {
                'schema_version': 'team-task@1', 'id': uid('teamtask'), 'workspace_id': 'ws_local',
                **body, 'requirements_digest': digest(dumps(body['requirements']).encode()),
                'gate_digest': digest(dumps(body['gate']).encode()), 'status': 'todo', 'assignee_id': None,
                'lease': None, 'closure': None, 'version': 1, 'handoff_count': 0, 'latest_gate_decision_id': None,
                'created_at': created_at, 'updated_at': created_at,
            }
            validate_contract('team_task', task)
            db.execute('INSERT INTO team_tasks VALUES(?,?,?)', (task['id'], task['parent_task_id'], dumps(task)))
            return task
        return self._idempotent('team-task:create', key, body, create)

    def tasks(self):
        return {'items': self.store.team_tasks(), 'runtime': self.runtime_status()}

    def detail(self, task_id):
        with self.store.transaction() as db:
            task = self._expire_lease(db, self._row_task(db, task_id))
            children = [json.loads(row['doc']) for row in db.execute(
                'SELECT doc FROM team_tasks WHERE parent_task_id=? ORDER BY rowid', (task_id,)).fetchall()]
            handoffs = [json.loads(row['doc']) for row in db.execute(
                'SELECT doc FROM team_task_handoffs WHERE task_id=? ORDER BY sequence', (task_id,)).fetchall()]
            decisions = [json.loads(row['doc']) for row in db.execute(
                'SELECT doc FROM team_task_gate_decisions WHERE task_id=? ORDER BY rowid', (task_id,)).fetchall()]
            result = {'task': task, 'children': children, 'handoffs': handoffs,
                      'gate_decisions': decisions, 'runtime': self.runtime_status()}
            validate_contract('team_task_detail', result)
            return result

    def claim(self, task_id, body, key):
        validate_contract('claim_request', body)
        reject_sensitive(body)

        def claim(db):
            task = self._expire_lease(db, self._row_task(db, task_id))
            if task['status'] not in {'todo', 'in_progress'}:
                raise Problem('TEAM_TASK_STATE_INVALID', '只有 todo 或待返工的 in_progress Task 可以认领。', 409)
            if task['status'] == 'in_progress' and task['assignee_id'] not in {None, body['actor_id']}:
                raise Problem('TEAM_TASK_CLAIM_CONFLICT', '该 Task 已由其他负责人等待返工，不能静默抢占。', 409)
            expires_at = (iso_now() + timedelta(seconds=body['lease_seconds'])).isoformat().replace('+00:00', 'Z')
            task['status'] = 'in_progress'
            task['assignee_id'] = body['actor_id']
            task['lease'] = {'id': uid('lease'), 'claimant_id': body['actor_id'], 'expires_at': expires_at}
            self._touch(task)
            self._write_task(db, task)
            return task
        return self._idempotent('team-task:' + task_id + ':claim', key, body, claim)

    def create_handoff(self, task_id, body, key):
        validate_contract('handoff_create_request', body)
        reject_sensitive(body)

        def create(db):
            task = self._expire_lease(db, self._row_task(db, task_id))
            self._assert_version(task, body['expected_task_version'])
            self._assert_active_claim(task, body['actor_id'])
            handoff = {
                'schema_version': 'task-handoff@1', 'id': uid('handoff'), 'task_id': task_id,
                'sequence': task['handoff_count'] + 1, 'actor_id': body['actor_id'], 'task_version': task['version'],
                'requirements_digest': task['requirements_digest'], 'gate_digest': task['gate_digest'],
                **{name: body[name] for name in ('summary', 'decisions', 'artifact_refs', 'evidence', 'remaining', 'risks', 'next_action')},
                'created_at': now(),
            }
            validate_contract('task_handoff', handoff)
            db.execute('INSERT INTO team_task_handoffs VALUES(?,?,?,?)',
                       (handoff['id'], task_id, handoff['sequence'], dumps(handoff)))
            task['handoff_count'] += 1
            self._touch(task)
            self._write_task(db, task)
            return {'task': task, 'handoff': handoff}
        return self._idempotent('team-task:' + task_id + ':handoff', key, body, create)

    def submit(self, task_id, body, key):
        validate_contract('submit_request', body)
        reject_sensitive(body)

        def submit(db):
            task = self._expire_lease(db, self._row_task(db, task_id))
            self._assert_version(task, body['expected_task_version'])
            self._assert_active_claim(task, body['actor_id'])
            if task['handoff_count'] == 0:
                raise Problem('TEAM_TASK_HANDOFF_REQUIRED', '提交审核前必须写入至少一份 Handoff。', 409)
            if self._open_children(db, task_id):
                raise Problem('TEAM_TASK_CHILDREN_OPEN', '仍有未结束 Child Task，父项不能提交审核。', 409)
            task['status'] = 'in_review'
            task['lease'] = None
            self._touch(task)
            self._write_task(db, task)
            return task
        return self._idempotent('team-task:' + task_id + ':submit', key, body, submit)

    def close(self, task_id, body, key):
        """Stop tracking a Team Task without representing delivery.

        This local-admin control-plane slice records the actor and reason. A
        later identity/policy layer must authorize the same state transition.
        """
        validate_contract('close_request', body)
        reject_sensitive(body)

        def close(db):
            task = self._expire_lease(db, self._row_task(db, task_id))
            self._assert_version(task, body['expected_task_version'])
            if task['status'] in TERMINAL:
                raise Problem('TEAM_TASK_STATE_INVALID', '已结束的 Task 不能再次关闭。', 409)
            if task['status'] == 'in_progress':
                self._assert_active_claim(task, body['actor_id'])
            elif task['status'] == 'in_review' and body['actor_id'] not in {
                    task['assignee_id'], task['gate']['reviewer_id']}:
                raise Problem('TEAM_TASK_CLOSE_FORBIDDEN', '审核中的 Task 仅负责人或 Gate reviewer 可以关闭。', 403)
            task['status'] = 'closed'
            task['lease'] = None
            task['closure'] = {'actor_id': body['actor_id'], 'reason': body['reason'], 'closed_at': now()}
            self._touch(task)
            self._write_task(db, task)
            return task
        return self._idempotent('team-task:' + task_id + ':close', key, body, close)

    def gate_decision(self, task_id, body, key):
        validate_contract('gate_decision_request', body)
        reject_sensitive(body)

        def decide(db):
            task = self._expire_lease(db, self._row_task(db, task_id))
            self._assert_version(task, body['expected_task_version'])
            if task['status'] != 'in_review':
                raise Problem('TEAM_TASK_STATE_INVALID', '只有 in_review Task 可以接受 Gate 决策。', 409)
            if task['gate']['reviewer_id'] != body['reviewer_id']:
                raise Problem('TEAM_TASK_GATE_FORBIDDEN', '只有预设 Gate reviewer 可以作出该决策。', 403)
            if body['decision'] == 'pass' and self._open_children(db, task_id):
                raise Problem('TEAM_TASK_CHILDREN_OPEN', '仍有未结束 Child Task，父项不能通过 Gate。', 409)
            decision = {
                'schema_version': 'task-gate-decision@1', 'id': uid('gate'), 'task_id': task_id,
                'task_version': task['version'], 'reviewer_id': body['reviewer_id'], 'decision': body['decision'],
                'requirements_digest': task['requirements_digest'], 'gate_digest': task['gate_digest'],
                'evidence': body['evidence'], 'reason': body['reason'], 'created_at': now(),
            }
            validate_contract('gate_decision', decision)
            db.execute('INSERT INTO team_task_gate_decisions VALUES(?,?,?)', (decision['id'], task_id, dumps(decision)))
            task['latest_gate_decision_id'] = decision['id']
            if body['decision'] == 'pass':
                task['status'], task['lease'] = 'done', None
            elif body['decision'] == 'reject':
                # The assignee remains responsible, but must explicitly claim a
                # fresh lease before further edits/handoffs are accepted.
                task['status'], task['lease'] = 'in_progress', None
            else:
                task['status'], task['lease'] = 'in_review', None
            self._touch(task)
            self._write_task(db, task)
            return {'task': task, 'decision': decision}
        return self._idempotent('team-task:' + task_id + ':gate-decision', key, body, decide)
