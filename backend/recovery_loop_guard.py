"""Evidence-driven recovery and anti-loop control plane.

This is deliberately a sidecar to Team Task/Handoff/Gate, not a general Agent
runtime or a second Product Run state machine.  A Try writes only a candidate
recovery route; Confirm revalidates immutable bindings but still executes no
tool; Cancel creates audit state only.  A normal Team Handoff and Gate pass
remain the only route by which a recovered result can be represented as
delivered.
"""
from __future__ import annotations

import json
from datetime import timedelta
from pathlib import Path

from jsonschema import Draft202012Validator, FormatChecker

from .analysis import Problem, digest
from .store import dumps, now, uid
from .team_coordination import TeamCoordination, iso_now, parse_time, reject_sensitive


ROOT = Path(__file__).resolve().parents[1]
CONTRACT = json.loads((ROOT / 'specs/v1/recovery-loop-guard.schema.json').read_text())
TERMINAL = {'resolved', 'cancelled'}
NO_TOOL_PERMISSION_SNAPSHOT = {
    'profile': 'recovery_no_tool_execution@1',
    'allow_tools': [],
    'deny_capabilities': ['network', 'package_install', 'external_write', 'host_path', 'secret'],
}

# The caller may identify a stable failure code, but never chooses whether it
# is retryable or which evidence category makes a candidate acceptable.
ERROR_CATALOG = {
    'EXECUTION_TIMEOUT': (True, 'retry_after_confirm', ['failure_event', 'operation_log', 'task_contract', 'input_digest', 'budget_snapshot']),
    'EXTERNAL_DEPENDENCY_TRANSIENT': (True, 'retry_after_confirm', ['failure_event', 'operation_log', 'task_contract', 'input_digest', 'budget_snapshot']),
    'REPEATED_OPERATION_FAILURE': (False, 'transfer_to_human', ['failure_event', 'operation_log', 'task_contract', 'budget_snapshot']),
    'CHECKPOINT_UNAVAILABLE': (False, 'collect_checkpoint_evidence', ['failure_event', 'checkpoint', 'task_contract', 'input_digest']),
    'PERMISSION_DENIED': (False, 'transfer_to_human', ['failure_event', 'task_contract', 'budget_snapshot']),
    'BUDGET_EXCEEDED': (False, 'transfer_to_human', ['failure_event', 'task_contract', 'budget_snapshot']),
    'CANCELLED': (False, 'cancel_and_audit', ['failure_event', 'task_contract']),
    'NO_VERIFIABLE_PROGRESS': (False, 'transfer_to_human', ['failure_event', 'operation_log', 'task_contract', 'budget_snapshot']),
}


def validate_contract(name, value):
    schema = {'$ref': '#/$defs/' + name, '$defs': CONTRACT['$defs']}
    errors = list(Draft202012Validator(schema, format_checker=FormatChecker()).iter_errors(value))
    if errors:
        raise Problem('RECOVERY_CONTRACT_INVALID', '请求不满足 Recovery Loop Guard 契约。', 422)


def error_contract(code):
    retryable, next_action, evidence = ERROR_CATALOG[code]
    return {
        'schema_version': 'error-contract@1', 'error_code': code, 'retryable': retryable,
        'recommended_next_action': next_action, 'required_evidence': evidence,
    }


class RecoveryLoopGuard:
    """A local, deterministic recovery-decision ledger with hard limits."""

    def __init__(self, store, team: TeamCoordination):
        self.store = store
        self.team = team

    @staticmethod
    def runtime_status():
        return {
            'mode': 'recovery_loop_guard@1', 'agent_runtime': 'not_connected',
            'external_model_calls': 0, 'external_tool_calls': 0,
            'automatic_recovery_execution': False,
            'note': 'Try 只记录候选路径；Confirm 只重验绑定；Cancel 只审计。不会启动模型、工具、恢复或自动审批。',
        }

    def _idempotent(self, scope, key, body, action):
        return self.team._idempotent(scope, key, body, action)

    @staticmethod
    def _row_case(db, case_id):
        row = db.execute('SELECT doc FROM recovery_cases WHERE id=?', (case_id,)).fetchone()
        if not row:
            raise Problem('RECOVERY_CASE_NOT_FOUND', 'Recovery Case 不存在。', 404)
        return json.loads(row['doc'])

    @staticmethod
    def _row_attempt(db, attempt_id):
        row = db.execute('SELECT doc FROM recovery_attempts WHERE id=?', (attempt_id,)).fetchone()
        if not row:
            raise Problem('RECOVERY_ATTEMPT_NOT_FOUND', 'Recovery Attempt 不存在。', 404)
        return json.loads(row['doc'])

    @staticmethod
    def _write_case(db, case):
        validate_contract('recovery_case', case)
        db.execute('UPDATE recovery_cases SET doc=? WHERE id=?', (dumps(case), case['id']))

    @staticmethod
    def _write_attempt(db, attempt):
        validate_contract('recovery_attempt', attempt)
        db.execute('UPDATE recovery_attempts SET doc=? WHERE id=?', (dumps(attempt), attempt['id']))

    @staticmethod
    def _touch(case):
        case['case_version'] += 1
        case['updated_at'] = now()

    @staticmethod
    def _assert_case_version(case, expected):
        if case['case_version'] != expected:
            raise Problem('RECOVERY_CASE_VERSION_CONFLICT', 'Recovery Case 已变化；请重新读取后再写入。', 409)

    @staticmethod
    def _assert_owner(case, actor_id):
        if case['owner_id'] != actor_id:
            raise Problem('RECOVERY_OWNER_REQUIRED', '只有记录该 Recovery Case 的负责人可以继续该恢复决策。', 403)

    def _trip_hard_stop(self, db, case, reason):
        if case['hard_stop']['tripped']:
            return case
        case['hard_stop'] = {'tripped': True, 'reason': reason, 'tripped_at': now()}
        if case['status'] not in TERMINAL:
            case['status'] = 'cancelled' if reason == 'cancelled' else 'needs_human'
        self._touch(case)
        self._write_case(db, case)
        return case

    def _expire_if_needed(self, db, case):
        if not case['hard_stop']['tripped'] and parse_time(case['deadline_at']) <= iso_now():
            return self._trip_hard_stop(db, case, 'elapsed_time_limit')
        return case

    def _assert_open(self, db, case):
        case = self._expire_if_needed(db, case)
        if case['hard_stop']['tripped']:
            raise Problem('RECOVERY_HARD_STOP', '恢复控制已被硬熔断；只能保留审计或转人工。', 409)
        if case['status'] != 'open':
            raise Problem('RECOVERY_CASE_STATE_INVALID', '当前 Recovery Case 不接受新的恢复候选。', 409)
        return case

    def _task_for_owner(self, db, case, actor_id, require_claim=True):
        task = self.team._expire_lease(db, self.team._row_task(db, case['team_task_id']))
        if require_claim:
            self.team._assert_active_claim(task, actor_id)
        return task

    @staticmethod
    def _scope_digest(task):
        return digest(dumps(task['scope']).encode())

    def _assert_binding(self, case, task, input_digest):
        binding = case['binding']
        if input_digest != binding['input_digest']:
            raise Problem('RECOVERY_INPUT_VERSION_CONFLICT', '输入摘要已变化；不能沿用旧恢复候选。', 409)
        if task['version'] != binding['task_version']:
            raise Problem('RECOVERY_TASK_VERSION_CONFLICT', 'Task 已变化；必须基于新的 Task 重新建立恢复决策。', 409)
        if (task['requirements_digest'] != binding['requirements_digest'] or task['gate_digest'] != binding['gate_digest']
                or self._scope_digest(task) != binding['scope_digest']):
            raise Problem('RECOVERY_TASK_CONTRACT_CONFLICT', 'Task requirements、Gate 或 scope 已变化；恢复候选失效。', 409)
        if digest(dumps(case['permission_snapshot']).encode()) != binding['permission_digest']:
            raise Problem('RECOVERY_PERMISSION_SNAPSHOT_CONFLICT', '固定的无工具权限快照不匹配；拒绝继续。', 409)

    @staticmethod
    def _checkpoint_valid(case, strategy):
        checkpoint = case['rollback_checkpoint']
        if checkpoint['availability'] == 'verified':
            return bool(checkpoint['checkpoint_ref'] and checkpoint['checkpoint_sha256'])
        return strategy != 'rollback_to_verified_checkpoint'

    def _assert_attempt_budget(self, db, case):
        case = self._expire_if_needed(db, case)
        if case['hard_stop']['tripped']:
            return None
        if case['recovery_attempt_count'] >= case['limits']['max_recovery_attempts']:
            self._trip_hard_stop(db, case, 'recovery_attempt_limit')
            return None
        if case['turn_count'] >= case['limits']['max_turns']:
            self._trip_hard_stop(db, case, 'turn_limit')
            return None
        return case

    @staticmethod
    def _last_attempt(db, case):
        if not case['latest_attempt_id']:
            return None
        return RecoveryLoopGuard._row_attempt(db, case['latest_attempt_id'])

    def _consecutive_failure_count(self, db, case_id, operation_ref, signature):
        rows = db.execute('SELECT doc FROM recovery_observations WHERE case_id=? ORDER BY rowid DESC', (case_id,)).fetchall()
        count = 0
        for row in rows:
            observation = json.loads(row['doc'])
            if observation['kind'] == 'verified_progress':
                break
            if observation['operation_ref'] != operation_ref or observation['signature_sha256'] != signature:
                break
            count += 1
        return count

    @staticmethod
    def _failures_since_verified_progress(db, case_id):
        """Count failed observations since the latest evidence-backed progress.

        This deliberately differs from the per-operation repetition guard: a
        caller cannot avoid a soft reminder merely by changing an operation
        label or signature while producing no verifiable progress.
        """
        rows = db.execute('SELECT doc FROM recovery_observations WHERE case_id=? ORDER BY rowid DESC', (case_id,)).fetchall()
        count = 0
        for row in rows:
            observation = json.loads(row['doc'])
            if observation['kind'] == 'verified_progress':
                break
            count += 1
        return count

    def create_case(self, body, key):
        validate_contract('recovery_case_create_request', body)
        reject_sensitive(body)
        if body['rollback_checkpoint']['availability'] == 'verified' and not (
                body['rollback_checkpoint']['checkpoint_ref'] and body['rollback_checkpoint']['checkpoint_sha256']):
            raise Problem('RECOVERY_CHECKPOINT_INVALID', 'verified Checkpoint 必须有引用和摘要。', 422)
        if body['rollback_checkpoint']['availability'] == 'unavailable' and (
                body['rollback_checkpoint']['checkpoint_ref'] is not None or body['rollback_checkpoint']['checkpoint_sha256'] is not None):
            raise Problem('RECOVERY_CHECKPOINT_INVALID', 'unavailable Checkpoint 不得伪造引用或摘要。', 422)

        def create(db):
            task = self.team._expire_lease(db, self.team._row_task(db, body['team_task_id']))
            self.team._assert_active_claim(task, body['actor_id'])
            created_at = now()
            permissions = dict(NO_TOOL_PERMISSION_SNAPSHOT)
            binding = {
                'team_task_id': task['id'], 'task_version': task['version'],
                'requirements_digest': task['requirements_digest'], 'gate_digest': task['gate_digest'],
                'scope_digest': self._scope_digest(task), 'input_digest': body['input_digest'],
                'permission_digest': digest(dumps(permissions).encode()),
            }
            contract = error_contract(body['failure_point']['error_code'])
            status = 'open' if contract['retryable'] else 'needs_human'
            deadline = (iso_now() + timedelta(seconds=body['limits']['max_elapsed_seconds'])).isoformat().replace('+00:00', 'Z')
            case = {
                'schema_version': 'recovery-case@1', 'id': uid('recovery'), 'team_task_id': task['id'],
                'owner_id': body['actor_id'], 'binding': binding, 'permission_snapshot': permissions,
                'limits': body['limits'], 'deadline_at': deadline, 'error_contract': contract,
                'failure_point': body['failure_point'], 'root_cause_hypothesis': body['root_cause_hypothesis'],
                'rollback_checkpoint': body['rollback_checkpoint'], 'replan_start': body['replan_start'],
                'status': status, 'case_version': 1, 'turn_count': 0, 'recovery_attempt_count': 0,
                'consecutive_failure_count': 0, 'hard_stop': {'tripped': False, 'reason': None, 'tripped_at': None},
                'latest_attempt_id': None, 'linked_handoff_id': None, 'linked_gate_decision_id': None,
                'created_at': created_at, 'updated_at': created_at,
            }
            validate_contract('recovery_case', case)
            db.execute('INSERT INTO recovery_cases VALUES(?,?,?)', (case['id'], task['id'], dumps(case)))
            return case
        return self._idempotent('recovery-case:create', key, body, create)

    def cases(self):
        with self.store.transaction() as db:
            items = []
            for row in db.execute('SELECT doc FROM recovery_cases ORDER BY rowid DESC').fetchall():
                items.append(self._expire_if_needed(db, json.loads(row['doc'])))
            result = {'items': items, 'runtime': self.runtime_status()}
            validate_contract('recovery_case_list', result)
            return result

    def detail(self, case_id):
        with self.store.transaction() as db:
            case = self._expire_if_needed(db, self._row_case(db, case_id))
            result = {
                'case': case,
                'attempts': [json.loads(row['doc']) for row in db.execute('SELECT doc FROM recovery_attempts WHERE case_id=? ORDER BY rowid', (case_id,)).fetchall()],
                'observations': [json.loads(row['doc']) for row in db.execute('SELECT doc FROM recovery_observations WHERE case_id=? ORDER BY rowid', (case_id,)).fetchall()],
                'reminders': [json.loads(row['doc']) for row in db.execute('SELECT doc FROM recovery_reminders WHERE case_id=? ORDER BY rowid', (case_id,)).fetchall()],
                'cancel_audits': [json.loads(row['doc']) for row in db.execute('SELECT doc FROM recovery_cancel_audits WHERE case_id=? ORDER BY rowid', (case_id,)).fetchall()],
                'runtime': self.runtime_status(),
            }
            validate_contract('recovery_case_detail', result)
            return result

    def observe(self, case_id, body, key):
        validate_contract('observation_create_request', body)
        reject_sensitive(body)

        def observe(db):
            case = self._row_case(db, case_id)
            self._assert_owner(case, body['actor_id'])
            self._assert_case_version(case, body['expected_case_version'])
            if case['status'] in TERMINAL or case['hard_stop']['tripped']:
                raise Problem('RECOVERY_CASE_STATE_INVALID', '结束或熔断的 Recovery Case 不再接收 Observation。', 409)
            case = self._expire_if_needed(db, case)
            if case['hard_stop']['tripped']:
                raise Problem('RECOVERY_HARD_STOP', '已达到时间硬上限；Observation 已停止。', 409)
            if body['turn'] <= case['turn_count'] or body['turn'] > case['limits']['max_turns']:
                raise Problem('RECOVERY_TURN_INVALID', 'turn 必须严格递增且不得超过冻结上限。', 409)
            observation = {
                'schema_version': 'recovery-observation@1', 'id': uid('recoveryobs'), 'case_id': case_id,
                'actor_id': body['actor_id'], 'kind': body['kind'], 'turn': body['turn'],
                'operation_ref': body['operation_ref'], 'signature_sha256': body['signature_sha256'],
                'evidence': body['evidence'], 'created_at': now(),
            }
            validate_contract('recovery_observation', observation)
            db.execute('INSERT INTO recovery_observations VALUES(?,?,?)', (observation['id'], case_id, dumps(observation)))
            reminder = None
            case['turn_count'] = body['turn']
            if body['kind'] == 'verified_progress':
                case['consecutive_failure_count'] = 0
            else:
                failures = self._consecutive_failure_count(db, case_id, body['operation_ref'], body['signature_sha256'])
                case['consecutive_failure_count'] = failures
                if failures >= case['limits']['max_repeated_operation_failures']:
                    self._trip_hard_stop(db, case, 'repeated_operation_limit')
                    return {'case': case, 'observation': observation, 'reminder': None}
                if failures >= 2:
                    reminder_reason = 'consecutive_failures'
                elif self._failures_since_verified_progress(db, case_id) >= 2:
                    reminder_reason = 'no_verifiable_progress'
                else:
                    reminder_reason = None
                if reminder_reason:
                    reminder = {
                        'schema_version': 'recovery-reminder@1', 'id': uid('recoveryreminder'), 'case_id': case_id,
                        'reason': reminder_reason, 'recommended_next_action': 'change_strategy_or_transfer_to_human',
                        'created_at': now(),
                    }
                    validate_contract('reminder', reminder)
                    db.execute('INSERT INTO recovery_reminders VALUES(?,?,?)', (reminder['id'], case_id, dumps(reminder)))
            if case['turn_count'] >= case['limits']['max_turns']:
                self._trip_hard_stop(db, case, 'turn_limit')
            else:
                self._touch(case)
                self._write_case(db, case)
            return {'case': case, 'observation': observation, 'reminder': reminder}
        return self._idempotent('recovery-case:' + case_id + ':observe', key, body, observe)

    def try_recovery(self, case_id, body, key):
        validate_contract('recovery_try_request', body)
        reject_sensitive(body)

        def attempt_create(db):
            case = self._row_case(db, case_id)
            self._assert_owner(case, body['actor_id'])
            self._assert_case_version(case, body['expected_case_version'])
            case = self._expire_if_needed(db, case)
            if case['hard_stop']['tripped']:
                return {'case': case, 'attempt': None, 'runtime': self.runtime_status()}
            if case['status'] != 'open':
                raise Problem('RECOVERY_CASE_STATE_INVALID', '当前 Recovery Case 不接受新的恢复候选。', 409)
            self._assert_attempt_budget(db, case)
            if case['hard_stop']['tripped']:
                return {'case': case, 'attempt': None, 'runtime': self.runtime_status()}
            task = self._task_for_owner(db, case, body['actor_id'])
            self._assert_binding(case, task, case['binding']['input_digest'])
            if body['strategy'] == 'retry_idempotent_step' and not case['error_contract']['retryable']:
                raise Problem('RECOVERY_NOT_RETRYABLE', '该 Error Contract 不允许重试；请转人工或澄清。', 409)
            if not self._checkpoint_valid(case, body['strategy']):
                raise Problem('RECOVERY_CHECKPOINT_UNAVAILABLE', '回滚候选必须绑定已验证的 Checkpoint。', 409)
            attempt = {
                'schema_version': 'recovery-attempt@1', 'id': uid('recoveryattempt'), 'case_id': case_id,
                'owner_id': body['actor_id'], 'case_version': case['case_version'], 'strategy': body['strategy'],
                'status': 'proposed',
                'validation': ['task_claim_active', 'task_contract_frozen', 'input_digest_bound', 'permission_snapshot_no_tools', 'budget_within_limit', 'candidate_only_no_execution'],
                'created_at': now(), 'updated_at': now(),
            }
            validate_contract('recovery_attempt', attempt)
            db.execute('INSERT INTO recovery_attempts VALUES(?,?,?)', (attempt['id'], case_id, dumps(attempt)))
            case['recovery_attempt_count'] += 1
            case['latest_attempt_id'] = attempt['id']
            self._touch(case)
            self._write_case(db, case)
            return {'case': case, 'attempt': attempt, 'runtime': self.runtime_status()}
        return self._idempotent('recovery-case:' + case_id + ':try', key, body, attempt_create)

    def confirm(self, case_id, body, key):
        validate_contract('recovery_confirm_request', body)
        reject_sensitive(body)

        def confirm_attempt(db):
            case = self._row_case(db, case_id)
            self._assert_owner(case, body['actor_id'])
            self._assert_case_version(case, body['expected_case_version'])
            case = self._assert_open(db, case)
            task = self._task_for_owner(db, case, body['actor_id'])
            self._assert_binding(case, task, body['input_digest'])
            if case['turn_count'] >= case['limits']['max_turns'] or case['recovery_attempt_count'] > case['limits']['max_recovery_attempts']:
                raise Problem('RECOVERY_BUDGET_EXCEEDED', '确认时发现恢复预算已耗尽。', 409)
            attempt = self._last_attempt(db, case)
            if not attempt or attempt['status'] != 'proposed':
                raise Problem('RECOVERY_CANDIDATE_REQUIRED', 'Confirm 必须绑定一个尚未确认的 Try 候选。', 409)
            if not self._checkpoint_valid(case, attempt['strategy']):
                raise Problem('RECOVERY_CHECKPOINT_UNAVAILABLE', '确认时 Checkpoint 不再满足回滚候选条件。', 409)
            attempt['status'] = 'confirmed'
            attempt['validation'].append('confirm_rechecked_task_checkpoint_permission_budget_input')
            attempt['updated_at'] = now()
            self._write_attempt(db, attempt)
            case['status'] = 'confirmed_pending_handoff'
            self._touch(case)
            self._write_case(db, case)
            return {'case': case, 'attempt': attempt, 'runtime': self.runtime_status()}
        return self._idempotent('recovery-case:' + case_id + ':confirm', key, body, confirm_attempt)

    def cancel(self, case_id, body, key):
        validate_contract('recovery_cancel_request', body)
        reject_sensitive(body)

        def cancel_attempt(db):
            case = self._row_case(db, case_id)
            self._assert_owner(case, body['actor_id'])
            self._assert_case_version(case, body['expected_case_version'])
            if case['status'] in TERMINAL:
                raise Problem('RECOVERY_CASE_STATE_INVALID', '已结束的 Recovery Case 不能再次取消。', 409)
            attempt = self._last_attempt(db, case)
            if not attempt or attempt['status'] not in {'proposed', 'confirmed'}:
                raise Problem('RECOVERY_CANDIDATE_REQUIRED', 'Cancel 只能审计当前未结束的恢复候选。', 409)
            attempt['status'] = 'cancelled'
            attempt['updated_at'] = now()
            self._write_attempt(db, attempt)
            audit = {
                'schema_version': 'recovery-cancel-audit@1', 'id': uid('recoverycancel'), 'case_id': case_id,
                'attempt_id': attempt['id'], 'actor_id': body['actor_id'], 'reason': body['reason'], 'created_at': now(),
            }
            validate_contract('recovery_cancel_audit', audit)
            db.execute('INSERT INTO recovery_cancel_audits VALUES(?,?,?)', (audit['id'], case_id, dumps(audit)))
            self._trip_hard_stop(db, case, 'cancelled')
            return {'case': case, 'attempt': attempt, 'cancel_audit': audit, 'runtime': self.runtime_status()}
        return self._idempotent('recovery-case:' + case_id + ':cancel', key, body, cancel_attempt)

    def link_handoff(self, case_id, body, key):
        validate_contract('link_handoff_request', body)
        reject_sensitive(body)

        def link(db):
            case = self._row_case(db, case_id)
            self._assert_owner(case, body['actor_id'])
            self._assert_case_version(case, body['expected_case_version'])
            if case['status'] != 'confirmed_pending_handoff':
                raise Problem('RECOVERY_HANDOFF_STATE_INVALID', '只有 Confirm 后的 Recovery Case 可以关联 Handoff。', 409)
            task = self._task_for_owner(db, case, body['actor_id'])
            row = db.execute('SELECT doc FROM team_task_handoffs WHERE id=? AND task_id=?', (body['handoff_id'], case['team_task_id'])).fetchone()
            if not row:
                raise Problem('RECOVERY_HANDOFF_NOT_FOUND', '同一 Team Task 中不存在该 Handoff。', 404)
            handoff = json.loads(row['doc'])
            binding = case['binding']
            if (handoff['actor_id'] != case['owner_id'] or handoff['task_version'] != binding['task_version']
                    or handoff['requirements_digest'] != binding['requirements_digest'] or handoff['gate_digest'] != binding['gate_digest']
                    or task['requirements_digest'] != binding['requirements_digest'] or task['gate_digest'] != binding['gate_digest']
                    or self._scope_digest(task) != binding['scope_digest']):
                raise Problem('RECOVERY_HANDOFF_BINDING_CONFLICT', 'Handoff 未绑定到原 Task 要求、Gate、范围和负责人。', 409)
            case['linked_handoff_id'] = handoff['id']
            case['status'] = 'recovery_reported'
            self._touch(case)
            self._write_case(db, case)
            return {'case': case, 'handoff': handoff, 'runtime': self.runtime_status()}
        return self._idempotent('recovery-case:' + case_id + ':link-handoff', key, body, link)

    def complete(self, case_id, body, key):
        validate_contract('complete_request', body)
        reject_sensitive(body)

        def complete_case(db):
            case = self._row_case(db, case_id)
            self._assert_owner(case, body['actor_id'])
            self._assert_case_version(case, body['expected_case_version'])
            if case['status'] != 'recovery_reported' or not case['linked_handoff_id']:
                raise Problem('RECOVERY_GATE_REQUIRED', '恢复结果必须先通过 Handoff 关联，且仍需正常 Gate。', 409)
            task = self.team._expire_lease(db, self.team._row_task(db, case['team_task_id']))
            row = db.execute('SELECT doc FROM team_task_gate_decisions WHERE id=? AND task_id=?', (body['gate_decision_id'], case['team_task_id'])).fetchone()
            if not row:
                raise Problem('RECOVERY_GATE_NOT_FOUND', '同一 Team Task 中不存在该 Gate 决策。', 404)
            decision = json.loads(row['doc'])
            binding = case['binding']
            if (task['status'] != 'done' or task['latest_gate_decision_id'] != decision['id'] or decision['decision'] != 'pass'
                    or decision['requirements_digest'] != binding['requirements_digest'] or decision['gate_digest'] != binding['gate_digest']):
                raise Problem('RECOVERY_GATE_NOT_PASSED', '重试或 Confirm 不代表交付；必须是同一 Task 的 Gate pass。', 409)
            case['linked_gate_decision_id'] = decision['id']
            case['status'] = 'resolved'
            self._touch(case)
            self._write_case(db, case)
            return {'case': case, 'gate_decision': decision, 'runtime': self.runtime_status()}
        return self._idempotent('recovery-case:' + case_id + ':complete', key, body, complete_case)
