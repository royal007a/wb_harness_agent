"""Control-plane policy, idempotency and bounded worker lifecycle."""
import json
import threading
import math
import copy
from datetime import datetime
from pathlib import Path

from jsonschema import Draft202012Validator, FormatChecker

from .analysis import Problem, analyze, artifacts, digest, parse_csv
from .execution_control import evaluate_try, transition_replan, validate_plan_graph
from .intent import IntentRouter
from adapters.contracts import AdapterRequest, validate_event, validate_result
from adapters.local import LocalAnalyticsAdapter
from .store import dumps, now, uid

ROOT = Path(__file__).resolve().parents[1]
BUNDLE = json.loads((ROOT / 'specs/v1/core-contracts.schema.json').read_text())
CONTROL = json.loads((ROOT / 'specs/v1/execution-control.schema.json').read_text())
TOOLS = ('resource.inspect', 'artifact.publish', 'run.final_answer')
DENY = ('network', 'package_install', 'external_write', 'host_path', 'secret')
TERMINAL = {'succeeded', 'failed', 'cancelled', 'expired'}


def capability_supported(value):
    return value is True or (isinstance(value, dict) and value.get('supported') is True)


def checkpoint_document_digest(checkpoint):
    """Hash all persisted, non-secret Checkpoint metadata except its self-hash."""
    return digest(dumps({key: value for key, value in checkpoint.items() if key != 'sha256'}).encode())


def plan_document_digest(plan):
    """Hash an immutable PlanRevision without trusting its stored self-hash."""
    return digest(dumps({key: value for key, value in plan.items() if key != 'plan_digest'}).encode())


def validate_control(kind, value):
    schema = {'$ref': '#/$defs/' + kind, '$defs': CONTROL['$defs']}
    errors = list(Draft202012Validator(schema, format_checker=FormatChecker()).iter_errors(value))
    if errors:
        raise Problem('CONTROL_CONTRACT_INVALID', 'Plan/Replan 控制对象不满足机器契约。', 409)


def limits_within(candidate, bound):
    return all(candidate[name] <= bound[name] for name in ('max_turns', 'timeout_seconds', 'max_input_tokens', 'max_cost_minor'))


def validate(kind, value):
    schema = {'$ref': '#/$defs/' + kind, '$defs': BUNDLE['$defs']}
    errors = list(Draft202012Validator(schema, format_checker=FormatChecker()).iter_errors(value))
    if errors:
        raise Problem('VALIDATION_ERROR', '请求不满足 ' + kind + ' 契约；请检查字段类型、必填项与未知字段。', 422)


def local_task(resource_id, objective, timeout=60):
    return {'project_id': 'prj_local', 'objective': objective, 'agent_spec_version': 'local_analytics@1',
            'context': {'resource_ids': [resource_id], 'variables': {}},
            'engine_policy': {'mode': 'explicit', 'engine_id': 'engine_mock_analytics', 'required_capabilities': ['artifacts.files']},
            'model_policy': {'text_and_code': 'none', 'vision': None, 'allow_fallback': False},
            'requested_permissions': {'profile': 'analysis_read_only', 'profile_version': 1, 'allow_tools': list(TOOLS), 'deny_capabilities': list(DENY)},
            'limits': {'max_turns': 3, 'timeout_seconds': timeout, 'max_input_tokens': 1, 'max_cost_minor': 0}}


class Service:
    def __init__(self, store):
        self.store = store
        self.stopping = threading.Event()
        self.thread = None
        self.adapters = {'engine_mock_analytics': LocalAnalyticsAdapter()}
        self.intent_router = IntentRouter()
        from .research import Research
        from .research_agents import ResearchAgents
        from .research_native import NativeResearch
        from .baidu_netdisk import BaiduNetdiskConnector
        from .agent_lab import LocalAgentLab
        from .agent_runtime import AgentRuntime
        from .external_skills import ExternalSkillRuntime
        from .memory import MemoryPlane
        from .team_coordination import TeamCoordination
        from .recovery_loop_guard import RecoveryLoopGuard
        self.research = Research(self)
        self.research_agents = ResearchAgents(self)
        self.research_native = NativeResearch(self)
        self.baidu_netdisk = BaiduNetdiskConnector(store)
        self.agent_lab = LocalAgentLab(store)
        self.agent_runtime = AgentRuntime(store)
        self.external_skills = ExternalSkillRuntime(store)
        self.memory = MemoryPlane(store)
        self.team = TeamCoordination(store)
        self.recovery = RecoveryLoopGuard(store, self.team)

    def resource(self, name, raw):
        if not isinstance(name, str) or not name.lower().endswith('.csv') or len(name) > 180 or '/' in name or '\\' in name:
            raise Problem('INVALID_RESOURCE', '请提供有效的 CSV 文件名。')
        headers, rows, encoding = parse_csv(raw)
        ident = 'res_' + digest(raw)
        doc = {'id': ident, 'name': name, 'sha256': digest(raw), 'size_bytes': len(raw),
               'data_class': 'Internal', 'row_count': len(rows), 'columns': headers, 'encoding': encoding, 'created_at': now()}
        with self.store.transaction() as db:
            db.execute('INSERT OR IGNORE INTO resources VALUES(?,?,?)', (ident, dumps(doc), raw))
        return self.store.get('resources', ident)

    def research_pdf_resource(self, name, raw):
        """Register a bounded, Public PDF only for the gated native research path."""
        if (not isinstance(name, str) or not name.lower().endswith('.pdf') or len(name) > 180
                or '/' in name or '\\' in name or not raw.startswith(b'%PDF-') or not 1 <= len(raw) <= 15 * 1024 * 1024):
            raise Problem('INVALID_RESOURCE', '请提供不超过 15 MiB 的有效 PDF 文件名和内容。', 422)
        ident = 'res_' + digest(raw)
        doc = {'id': ident, 'name': name, 'sha256': digest(raw), 'size_bytes': len(raw),
               'data_class': 'Public', 'row_count': 0, 'columns': [], 'encoding': 'binary/pdf', 'created_at': now()}
        with self.store.transaction() as db:
            db.execute('INSERT OR IGNORE INTO resources VALUES(?,?,?)', (ident, dumps(doc), raw))
        return self.store.get('resources', ident)

    def interpret_intent(self, body):
        """Resolve only a registered CSV reference; the router has no side effects."""
        request = {name: body[name] for name in ('objective', 'resource_id') if name in body}
        resource = None
        if request.get('resource_id'):
            resource = self.store.get('resources', request['resource_id'])
            if not resource['name'].lower().endswith('.csv'):
                raise Problem('INVALID_RESOURCE', '意图预检只接受已登记 CSV 资源。', 422)
        return self.intent_router.interpret(request, resource)

    def idempotent(self, scope, key, body, action):
        if not key or len(key) > 128:
            raise Problem('VALIDATION_ERROR', '必须提供 1–128 字符的 Idempotency-Key。', 422)
        hashed = digest(dumps(body).encode())
        with self.store.transaction() as db:
            old = db.execute('SELECT digest,response FROM idempotency WHERE scope=? AND key=?', (scope, key)).fetchone()
            if old:
                if old['digest'] != hashed:
                    raise Problem('CONFLICT', '同一幂等键已用于不同请求。', 409)
                return json.loads(old['response'])
            result = action(db)
            db.execute('INSERT INTO idempotency VALUES(?,?,?,?)', (scope, key, hashed, dumps(result)))
            return result

    def create_task(self, body, key):
        validate('task_create', body)
        if body['project_id'] != 'prj_local' or body['agent_spec_version'] != 'local_analytics@1':
            raise Problem('FORBIDDEN', '初版只开放本地项目和固定分析 Agent。', 403)
        if body['engine_policy']['engine_id'] != 'engine_mock_analytics':
            raise Problem('ENGINE_UNAVAILABLE', '该引擎尚未通过接入探针。', 409)
        if set(body['engine_policy']['required_capabilities']) - {'artifacts.files', 'actions.tool_call', 'output.structured', 'control.cancel'}:
            raise Problem('ENGINE_UNAVAILABLE', '所需能力不可用。', 409)
        if body['model_policy'] != {'text_and_code': 'none', 'vision': None, 'allow_fallback': False}:
            raise Problem('MODEL_CAPABILITY_MISMATCH', '本地分析器不调用模型。', 409)
        permissions = body['requested_permissions']
        if set(permissions['allow_tools']) != set(TOOLS):
            raise Problem('FORBIDDEN', '该分析器需要且仅允许三个受控工具。', 403)
        if set(permissions['deny_capabilities']) - set(DENY):
            raise Problem('FORBIDDEN', '无法解析额外的拒绝能力，已拒绝执行。', 403)
        if len(body['context']['resource_ids']) != 1 or body['context']['variables']:
            raise Problem('VALIDATION_ERROR', '仅支持单 CSV，variables 必须为空。', 422)
        if not body['objective'].strip() or len(body['objective']) > 2000:
            raise Problem('VALIDATION_ERROR', '目标长度必须为 1–2000 字。', 422)
        if body['limits']['timeout_seconds'] > 300:
            raise Problem('VALIDATION_ERROR', '本地运行超时上限为 300 秒。', 422)
        resource = self.store.get('resources', body['context']['resource_ids'][0])
        if not resource['name'].lower().endswith('.csv'):
            raise Problem('INVALID_RESOURCE', '固定分析器只接受 CSV，不接受研究演示资料。', 422)
        if body.get('parent_task_id'):
            self.store.get('tasks', body['parent_task_id'])

        def create(db):
            task = {**body, 'id': uid('task'), 'created_at': now()}
            db.execute('INSERT INTO tasks VALUES(?,?)', (task['id'], dumps(task)))
            run = self.new_run(db, task)
            return {'task': task, 'initial_run': run}
        return self.idempotent('tasks', key, body, create)

    def new_run(self, db, task, based_on=None, restored_from_checkpoint=None, restored_limits=None,
                plan_revision_id=None, replan_attempt_id=None):
        if task['engine_policy']['engine_id'] == 'engine_local_research_demo':
            return self.research.new_run(db, task, based_on)
        if task['engine_policy']['engine_id'] == 'engine_research_multi_agent_simulation':
            return self.research_agents.new_run(db, task, based_on)
        if task['engine_policy']['engine_id'] == 'engine_claude_research_native':
            return self.research_native.new_run(db, task, based_on)
        active = [r for r in self.store.listing('runs') if r['status'] not in TERMINAL]
        if len(active) >= 32:
            raise Problem('RATE_LIMITED', '本地待执行队列已满（32）。', 429)
        attempts = [r for r in self.store.listing('runs') if r['task_id'] == task['id']]
        policy = {'profile_id': 'analysis_read_only', 'profile_version': 1, 'allowed_tools': list(TOOLS),
                  'denied_capabilities': list(DENY), 'decision_digest': digest(dumps(task['requested_permissions']).encode())}
        limits = copy.deepcopy(restored_limits if restored_limits is not None else task['limits'])
        base_plan = None
        if plan_revision_id is None:
            # Every newly created local Run has one immutable baseline Plan.  A
            # confirmed Replan passes its already-persisted candidate instead.
            base_plan = self._plan_revision(task, 1, self._local_base_plan_nodes())
            plan_revision_id = base_plan['id']
        run = {'id': uid('run'), 'task_id': task['id'], 'status': 'queued', 'selected_engine': 'engine_mock_analytics',
               'selected_models': {}, 'effective_permissions': policy, 'effective_limits': limits,
               'attempt_number': len(attempts) + 1, 'based_on_run_id': based_on,
               'restored_from_checkpoint_id': restored_from_checkpoint, 'plan_revision_id': plan_revision_id,
               'replan_attempt_id': replan_attempt_id, 'consumed_turns': 0, 'latest_sequence': 0,
               'exit_reason': None, 'created_at': now(), 'updated_at': now()}
        validate('run', run)
        db.execute('INSERT INTO runs VALUES(?,?,?)', (run['id'], task['id'], dumps(run)))
        if base_plan is not None:
            self.store.put_plan_revision(db, run['id'], base_plan)
        descriptor = self.adapters[run['selected_engine']].describe()
        validate('adapter_description', descriptor)
        queued = {'engine': run['selected_engine'], 'adapter': descriptor,
                  'adapter_digest': digest(dumps(descriptor).encode())}
        if restored_from_checkpoint:
            queued['restored_from_checkpoint_id'] = restored_from_checkpoint
        if plan_revision_id:
            queued['plan_revision_id'] = plan_revision_id
        if replan_attempt_id:
            queued['replan_attempt_id'] = replan_attempt_id
        self.store.event(db, run, 'run.queued', queued)
        return run

    def rerun(self, task_id, body, key):
        if not isinstance(body, dict) or set(body) - {'based_on_run_id', 'reason'}:
            raise Problem('VALIDATION_ERROR', '重跑参数无效。', 422)
        if 'reason' in body and (not isinstance(body['reason'], str) or len(body['reason']) > 2000):
            raise Problem('VALIDATION_ERROR', 'reason 必须为不超过 2000 字符的文本。', 422)
        task = self.store.get('tasks', task_id)
        based = body.get('based_on_run_id')
        if based is not None and (not isinstance(based, str) or self.store.get('runs', based)['task_id'] != task_id):
            raise Problem('VALIDATION_ERROR', 'based_on_run_id 必须属于该 Task。', 422)
        return self.idempotent('rerun:' + task_id, key, body, lambda db: self.new_run(db, task, based))

    def cancel(self, run_id):
        engine = self.store.get('runs', run_id)['selected_engine']
        if engine == 'engine_local_research_demo':
            return self.research.cancel(run_id)
        if engine == 'engine_research_multi_agent_simulation':
            return self.research_agents.cancel(run_id)
        if engine == 'engine_claude_research_native':
            return self.research_native.cancel(run_id)
        with self.store.transaction() as db:
            run = self.store.get('runs', run_id)
            if run['status'] not in TERMINAL:
                run['status'], run['exit_reason'] = 'cancelled', 'USER_CANCELLED'
                self.store.event(db, run, 'run.cancelled')
        adapter = self.adapters.get(run['selected_engine'])
        if adapter and run['status'] == 'cancelled':
            adapter.cancel_run(run_id)
        return run

    def check(self, run_id):
        run = self.store.get('runs', run_id)
        if self.stopping.is_set():
            raise Problem('SERVER_STOPPING', '服务正在停止。')
        if run['status'] in TERMINAL:
            raise Problem('CANCELLED', '运行已结束。')
        age = (datetime.now().astimezone() - datetime.fromisoformat(run['created_at'].replace('Z', '+00:00'))).total_seconds()
        if age >= run['effective_limits']['timeout_seconds']:
            raise Problem('TIMEOUT', '运行超过时间预算。')

    def stage(self, run_id, tool):
        with self.store.transaction() as db:
            self.check(run_id)
            run = self.store.get('runs', run_id)
            if tool not in run['effective_permissions']['allowed_tools']:
                raise Problem('FORBIDDEN', '工具未获授权。', 403)
            if run.get('consumed_turns', 0) >= run['effective_limits']['max_turns']:
                raise Problem('BUDGET_EXCEEDED', '运行已耗尽工具步骤预算。')
            step_id = uid('step')
            run['consumed_turns'] = run.get('consumed_turns', 0) + 1
            self.store.event(db, run, 'tool.call.completed', {'tool': tool, 'implementation': 'deterministic'}, step_id)
            return step_id

    def remaining_limits(self, run):
        created = datetime.fromisoformat(run['created_at'].replace('Z', '+00:00'))
        elapsed = max(0, math.ceil((datetime.now().astimezone() - created).total_seconds()))
        limits = run['effective_limits']
        return {
            'max_turns': max(0, limits['max_turns'] - run.get('consumed_turns', 0)),
            'timeout_seconds': max(0, limits['timeout_seconds'] - elapsed),
            # The fixed adapter makes no model calls, so it consumes neither value.
            'max_input_tokens': limits['max_input_tokens'],
            'max_cost_minor': limits['max_cost_minor'],
        }

    def create_checkpoint(self, run_id, task, resource, descriptor, request, adapter, result, completed_step_id):
        """Persist the only approved local checkpoint after the inspected input boundary."""
        state = adapter.checkpoint_run(request, result)
        state_bytes = dumps(state).encode()
        with self.store.transaction() as db:
            self.check(run_id)
            run = self.store.get('runs', run_id)
            remaining = self.remaining_limits(run)
            checkpoint_id = uid('ckpt')
            bindings = {
                'task_id': task['id'],
                'task_digest': digest(dumps(task).encode()),
                'resource_id': resource['id'],
                'resource_sha256': resource['sha256'],
                'adapter_digest': digest(dumps(descriptor).encode()),
                'effective_permissions_digest': digest(dumps(run['effective_permissions']).encode()),
                'source_effective_limits_digest': digest(dumps(run['effective_limits']).encode()),
                'remaining_limits_digest': digest(dumps(remaining).encode()),
            }
            checkpoint = {
                'id': checkpoint_id,
                'run_id': run_id,
                'event_sequence': run['latest_sequence'],
                'adapter_id': descriptor['adapter_id'],
                'adapter_version': descriptor['adapter_version'],
                'state_ref': 'sqlite:checkpoints/' + checkpoint_id,
                'state_sha256': digest(state_bytes),
                'completed_step_ids': [completed_step_id],
                'pending_action': {'id': 'artifact.publish', 'contract_version': 'local_analytics_restore@1'},
                'remaining_limits': remaining,
                'bindings': bindings,
                'compatibility_digest': digest(dumps(bindings).encode()),
                'sha256': '',
                'created_at': now(),
            }
            checkpoint['sha256'] = checkpoint_document_digest(checkpoint)
            validate('checkpoint', checkpoint)
            self.store.put_checkpoint(db, checkpoint, state_bytes)
            self.store.event(db, run, 'checkpoint.proposed', {
                'checkpoint_id': checkpoint_id,
                'checkpoint_sha256': checkpoint['sha256'],
                'state_sha256': checkpoint['state_sha256'],
                'restorable': remaining['max_turns'] >= 2 and remaining['timeout_seconds'] >= 1,
            }, completed_step_id)
        return checkpoint

    def load_restorable_checkpoint(self, source_run_id):
        """Read and mechanically verify every binding before a restore Run is created."""
        source = self.store.get('runs', source_run_id)
        if source['selected_engine'] != 'engine_mock_analytics' or source['status'] not in {'failed', 'expired'}:
            raise Problem('CHECKPOINT_NOT_RESTORABLE', '只有失败或超时的固定分析 Run 可以从 Checkpoint 恢复。', 409)
        checkpoint = self.store.latest_checkpoint(source_run_id)
        if checkpoint is None:
            raise Problem('CHECKPOINT_NOT_FOUND', '该 Run 没有可恢复的 Checkpoint。', 409)
        state_bytes = self.store.checkpoint_state(checkpoint['id'])
        try:
            state = json.loads(state_bytes)
        except (TypeError, ValueError, UnicodeDecodeError):
            raise Problem('CHECKPOINT_STATE_INVALID', 'Checkpoint 状态无法解析。', 409) from None
        if digest(state_bytes) != checkpoint['state_sha256'] or checkpoint_document_digest(checkpoint) != checkpoint['sha256']:
            raise Problem('CHECKPOINT_INCOMPATIBLE', 'Checkpoint 内容摘要不匹配。', 409)
        task = self.store.get('tasks', source['task_id'])
        resource_id = task['context']['resource_ids'][0]
        resource = self.store.get('resources', resource_id)
        raw = self.store.raw(resource_id)
        adapter = self.adapters.get(source['selected_engine'])
        if adapter is None:
            raise Problem('ENGINE_UNAVAILABLE', '原 Run 绑定的适配器当前不可用。', 409)
        descriptor = adapter.describe()
        capabilities = descriptor.get('capabilities', {})
        if not (capability_supported(capabilities.get('state.checkpoint'))
                and capability_supported(capabilities.get('state.restore'))):
            raise Problem('CHECKPOINT_INCOMPATIBLE', '适配器不再声明兼容的 checkpoint/restore 能力。', 409)
        remaining = checkpoint['remaining_limits']
        expected_policy = {
            'profile_id': 'analysis_read_only', 'profile_version': 1, 'allowed_tools': list(TOOLS),
            'denied_capabilities': list(DENY), 'decision_digest': digest(dumps(task['requested_permissions']).encode()),
        }
        expected_bindings = {
            'task_id': task['id'],
            'task_digest': digest(dumps(task).encode()),
            'resource_id': resource['id'],
            'resource_sha256': resource['sha256'],
            'adapter_digest': digest(dumps(descriptor).encode()),
            'effective_permissions_digest': digest(dumps(source['effective_permissions']).encode()),
            'source_effective_limits_digest': digest(dumps(source['effective_limits']).encode()),
            'remaining_limits_digest': digest(dumps(remaining).encode()),
        }
        source_tool_steps = sum(event['event_type'] == 'tool.call.completed'
                                for event in self.store.events(source_run_id)
                                if event['sequence'] <= checkpoint['event_sequence'])
        if (checkpoint['bindings'] != expected_bindings
                or checkpoint['compatibility_digest'] != digest(dumps(expected_bindings).encode())
                or checkpoint['adapter_id'] != descriptor['adapter_id']
                or checkpoint['adapter_version'] != descriptor['adapter_version']
                or checkpoint['run_id'] != source_run_id
                or checkpoint['state_ref'] != 'sqlite:checkpoints/' + checkpoint['id']
                or source['effective_permissions'] != expected_policy
                or not limits_within(source['effective_limits'], task['limits'])
                or not limits_within(remaining, source['effective_limits'])
                or remaining['max_turns'] != source['effective_limits']['max_turns'] - source_tool_steps
                or digest(raw) != resource['sha256']):
            raise Problem('CHECKPOINT_INCOMPATIBLE', 'Checkpoint 与当前 Task、资源、策略或适配器不兼容。', 409)
        if remaining['max_turns'] < 2 or remaining['timeout_seconds'] < 1:
            raise Problem('BUDGET_EXCEEDED', 'Checkpoint 的剩余预算不足以完成固定发布路径。', 409)
        expected_state = {'state_version': 'local_analytics_checkpoint@1', 'metrics': analyze(raw)}
        if dumps(state) != dumps(expected_state):
            raise Problem('CHECKPOINT_STATE_INVALID', 'Checkpoint 状态与固定输入回算不一致。', 409)
        return source, checkpoint, state, task, resource, raw, descriptor, adapter

    @staticmethod
    def _local_base_plan_nodes():
        return [
            {'id': 'node_inspect', 'action_id': 'resource.inspect', 'depends_on': [],
             'hard_preconditions': [], 'soft_preconditions': [], 'success_criteria': ['resource_verified'],
             'evidence_requirements': ['source_hash'], 'risk': 'read', 'idempotency': 'required'},
            {'id': 'node_publish', 'action_id': 'artifact.publish', 'depends_on': ['node_inspect'],
             'hard_preconditions': ['resource_verified'], 'soft_preconditions': [], 'success_criteria': ['artifacts_valid'],
             'evidence_requirements': ['artifact_hash'], 'risk': 'write', 'idempotency': 'required'},
            {'id': 'node_finalanswer', 'action_id': 'run.final_answer', 'depends_on': ['node_publish'],
             'hard_preconditions': ['artifacts_valid'], 'soft_preconditions': [], 'success_criteria': ['answer_committed'],
             'evidence_requirements': ['result_summary'], 'risk': 'write', 'idempotency': 'required'},
        ]

    @staticmethod
    def _local_recovery_plan_nodes():
        return [
            {'id': 'node_checkpointverify', 'action_id': 'checkpoint.verify', 'depends_on': [],
             'hard_preconditions': ['checkpoint_present'], 'soft_preconditions': [], 'success_criteria': ['checkpoint_verified'],
             'evidence_requirements': ['checkpoint_binding'], 'risk': 'read', 'idempotency': 'required'},
            {'id': 'node_publish', 'action_id': 'artifact.publish', 'depends_on': ['node_checkpointverify'],
             'hard_preconditions': ['checkpoint_verified'], 'soft_preconditions': [], 'success_criteria': ['artifacts_valid'],
             'evidence_requirements': ['artifact_hash'], 'risk': 'write', 'idempotency': 'required'},
            {'id': 'node_finalanswer', 'action_id': 'run.final_answer', 'depends_on': ['node_publish'],
             'hard_preconditions': ['artifacts_valid'], 'soft_preconditions': [], 'success_criteria': ['answer_committed'],
             'evidence_requirements': ['result_summary'], 'risk': 'write', 'idempotency': 'required'},
        ]

    def _plan_revision(self, task, revision, nodes, based_on=None):
        plan = {
            'contract_version': 'plan-revision@1', 'id': uid('plan'), 'task_id': task['id'], 'revision': revision,
            'based_on_plan_revision_id': based_on, 'nodes': nodes, 'plan_digest': '', 'created_at': now(),
        }
        plan['plan_digest'] = plan_document_digest(plan)
        validate_control('plan_revision', plan)
        validate_plan_graph(plan['nodes'])
        return plan

    @staticmethod
    def _failure_event(events, source):
        for event in reversed(events):
            if event['event_type'] in {'run.failed', 'run.expired'} and event['data'].get('error_code') == source['exit_reason']:
                return event
        raise Problem('REPLAN_FAILURE_EVIDENCE_MISSING', '源 Run 缺少可验证的终态失败 Evidence。', 409)

    @staticmethod
    def _gap_shape_is_compatible(gap, source_run_id):
        return (gap['run_id'] == source_run_id and gap['required_by'] == 'node_publish'
                and gap['type'] == 'evidence' and gap['severity'] == 'core'
                and gap['resolvable_action_ids'] == ['artifact.publish'])

    def _artifact_failure_gap(self, db, source, failure_event):
        """Persist exactly one redacted core Gap for the approved failure branch."""
        existing = self.store.gap_for_failure_event(source['id'], failure_event['event_id'])
        if existing is not None:
            return existing
        gap = {
            'contract_version': 'gap@1', 'id': uid('gap'), 'run_id': source['id'],
            'required_by': 'node_publish', 'type': 'evidence', 'severity': 'core',
            'resolvable_action_ids': ['artifact.publish'], 'status': 'open', 'created_at': now(),
        }
        validate_control('gap', gap)
        self.store.put_gap(db, gap, failure_event['event_id'])
        return gap

    def _verified_artifact_gap(self, source, failure_event, require_open=True):
        gap = self.store.gap_for_failure_event(source['id'], failure_event['event_id'])
        if gap is None or not self._gap_shape_is_compatible(gap, source['id']):
            raise Problem('REPLAN_GAP_INVALID', '源 Run 的 Gap State 缺失或不兼容。', 409)
        validate_control('gap', gap)
        if require_open and gap['status'] != 'open':
            raise Problem('REPLAN_GAP_NOT_OPEN', '该失败缺口已经不是可恢复状态。', 409)
        return gap

    def _replan_binding(self, source, checkpoint, task, resource, descriptor, candidate_plan):
        return {
            'origin_run_id': source['id'], 'checkpoint_id': checkpoint['id'],
            'checkpoint_sha256': checkpoint['sha256'], 'candidate_plan_revision_id': candidate_plan['id'],
            'candidate_plan_digest': candidate_plan['plan_digest'], 'task_id': task['id'],
            'task_digest': digest(dumps(task).encode()), 'resource_id': resource['id'],
            'resource_sha256': resource['sha256'], 'adapter_digest': digest(dumps(descriptor).encode()),
            'effective_permissions_digest': digest(dumps(source['effective_permissions']).encode()),
            'remaining_limits_digest': digest(dumps(checkpoint['remaining_limits']).encode()),
        }

    @staticmethod
    def _replan_response(attempt):
        return {
            'replan_id': attempt['id'], 'origin_run_id': attempt['origin_run_id'],
            'checkpoint_id': attempt['rollback_checkpoint_id'],
            'candidate_plan_revision_id': attempt['candidate_plan_revision_id'],
            'candidate_plan_digest': attempt['candidate_plan_digest'], 'status': attempt['status'],
        }

    def _load_replan_context(self, replan_id):
        attempt = self.store.replan_attempt(replan_id)
        source, checkpoint, state, task, resource, raw, descriptor, adapter = self.load_restorable_checkpoint(attempt['origin_run_id'])
        origin_plan = self.store.plan_revision(attempt['origin_plan_revision_id'])
        candidate_plan = self.store.plan_revision(attempt['candidate_plan_revision_id'])
        evidence = self.store.control_evidence(attempt['root_cause_evidence_ids'][0])
        events = self.store.events(source['id'])
        failure_event = self._failure_event(events, source)
        self._verified_artifact_gap(source, failure_event)
        if (attempt['rollback_checkpoint_id'] != checkpoint['id'] or attempt['failure_event_id'] != failure_event['event_id']
                or evidence['run_id'] != source['id'] or evidence['kind'] != 'event'
                or evidence['ref_id'] != failure_event['event_id'] or evidence['reliability'] != 'verified'
                or evidence['validation_status'] != 'passed'
                or evidence['content_sha256'] != digest(dumps(failure_event).encode())
                or source['exit_reason'] != 'ARTIFACT_PUBLICATION_FAILED'
                or source.get('plan_revision_id') != origin_plan['id']
                or origin_plan['plan_digest'] != plan_document_digest(origin_plan)
                or candidate_plan['plan_digest'] != plan_document_digest(candidate_plan)
                or candidate_plan['task_id'] != task['id']
                or candidate_plan['based_on_plan_revision_id'] != origin_plan['id']
                or candidate_plan['nodes'] != self._local_recovery_plan_nodes()):
            raise Problem('REPLAN_BINDING_INCOMPATIBLE', 'Replan 的失败 Evidence、计划或 Checkpoint 绑定不兼容。', 409)
        validate_control('replan_attempt', attempt)
        validate_plan_graph(origin_plan['nodes'])
        validate_plan_graph(candidate_plan['nodes'])
        return attempt, source, checkpoint, state, task, resource, raw, descriptor, adapter, candidate_plan

    def _try_outcome(self, attempt, source, checkpoint, task, resource, descriptor, candidate_plan):
        binding = self._replan_binding(source, checkpoint, task, resource, descriptor, candidate_plan)
        context = {
            'checkpoint_reliability': 'verified', 'adapter_capabilities': descriptor['capabilities'],
            'candidate_plan_digest_present': candidate_plan['plan_digest'] == plan_document_digest(candidate_plan),
            'candidate_permissions': ['artifact.publish', 'run.final_answer'],
            'origin_permissions': source['effective_permissions']['allowed_tools'],
            'candidate_budget': 2, 'remaining_budget': checkpoint['remaining_limits']['max_turns'],
            'compatibility_digest_matches': checkpoint['compatibility_digest'] == digest(dumps(checkpoint['bindings']).encode()),
        }
        outcome = evaluate_try(context, candidate_plan['nodes'])
        outcome['failure_event_id'] = attempt['failure_event_id']
        outcome['binding_digest'] = digest(dumps(binding).encode())
        return outcome, binding

    def propose_replan(self, source_run_id, body, key):
        if not isinstance(body, dict) or body:
            raise Problem('VALIDATION_ERROR', '本地 Replan 不接受调用方提交 Plan 或参数。', 422)

        def create(db):
            active = next((item for item in self.store.replan_attempts(source_run_id)
                           if item['status'] in {'proposed', 'trying', 'awaiting_confirmation'}), None)
            if active:
                return self._replan_response(active)
            source, checkpoint, _state, task, _resource, _raw, _descriptor, _adapter = self.load_restorable_checkpoint(source_run_id)
            if source['exit_reason'] != 'ARTIFACT_PUBLICATION_FAILED':
                raise Problem('REPLAN_ROOT_CAUSE_UNSUPPORTED', '只有已识别的产物构建失败可以进入本地 Replan。', 409)
            if any(run.get('restored_from_checkpoint_id') == checkpoint['id'] for run in self.store.listing('runs')):
                raise Problem('REPLAN_ALREADY_MATERIALIZED', '该 Checkpoint 已经创建过恢复 Run。', 409)
            failure_event = self._failure_event(self.store.events(source_run_id), source)
            self._verified_artifact_gap(source, failure_event)
            evidence = {
                'contract_version': 'evidence@1', 'id': uid('evi'), 'run_id': source['id'], 'kind': 'event',
                'ref_id': failure_event['event_id'], 'content_sha256': digest(dumps(failure_event).encode()),
                'reliability': 'verified', 'validation_status': 'passed', 'data_class': 'Internal', 'created_at': now(),
            }
            validate_control('evidence', evidence)
            origin_plan_id = source.get('plan_revision_id')
            if origin_plan_id is None:
                # Legacy rows created before ADR-0019 get the same fixed baseline
                # projection exactly once; no goal or execution state is changed.
                origin_plan = self._plan_revision(task, 1, self._local_base_plan_nodes())
                source['plan_revision_id'] = origin_plan['id']
                validate('run', source)
                db.execute('UPDATE runs SET doc=? WHERE id=?', (dumps(source), source['id']))
                self.store.put_plan_revision(db, source['id'], origin_plan)
            else:
                origin_plan = self.store.plan_revision(origin_plan_id)
                if origin_plan['task_id'] != task['id'] or origin_plan['nodes'] != self._local_base_plan_nodes():
                    raise Problem('REPLAN_BINDING_INCOMPATIBLE', '源 Run 的固定基线计划不兼容。', 409)
            candidate_plan = self._plan_revision(task, 2, self._local_recovery_plan_nodes(), origin_plan['id'])
            attempt = {
                'contract_version': 'replan-attempt@1', 'id': uid('rpl'), 'origin_run_id': source['id'],
                'origin_plan_revision_id': origin_plan['id'], 'failure_event_id': failure_event['event_id'],
                'root_cause_evidence_ids': [evidence['id']], 'root_cause_confidence': 'medium',
                'rollback_checkpoint_id': checkpoint['id'], 'replan_start_node_id': 'node_checkpointverify',
                'invalidated_node_ids': ['node_publish', 'node_finalanswer'],
                'candidate_plan_revision_id': candidate_plan['id'], 'candidate_plan_digest': candidate_plan['plan_digest'],
                'try_result_digest': None, 'confirmation_binding_digest': None, 'confirmed_run_id': None,
                'status': 'proposed', 'created_at': now(),
            }
            validate_control('replan_attempt', attempt)
            self.store.put_control_evidence(db, evidence)
            self.store.put_plan_revision(db, source['id'], candidate_plan)
            self.store.put_replan_attempt(db, attempt)
            return self._replan_response(attempt)

        return self.idempotent('replan-propose:' + source_run_id, key, body, create)

    def replans(self, source_run_id):
        return {'items': [self._replan_response(item) for item in self.store.replan_attempts(source_run_id)]}

    def replan(self, replan_id):
        attempt = self.store.replan_attempt(replan_id)
        candidate = self.store.plan_revision(attempt['candidate_plan_revision_id'])
        source = self.store.get('runs', attempt['origin_run_id'])
        failure_event = self._failure_event(self.store.events(source['id']), source)
        gap = self._verified_artifact_gap(source, failure_event, require_open=False)
        return {'attempt': attempt, 'candidate_plan': candidate, 'gaps': [gap]}

    def try_replan(self, replan_id, body, key):
        if not isinstance(body, dict) or body:
            raise Problem('VALIDATION_ERROR', 'Try 不接受调用方参数。', 422)

        def attempt_try(db):
            attempt = self.store.replan_attempt(replan_id)
            if attempt['status'] == 'awaiting_confirmation':
                return {'replan_id': attempt['id'], 'status': attempt['status'],
                        'try_result_digest': attempt['try_result_digest'],
                        'confirmation_binding_digest': attempt['confirmation_binding_digest']}
            if attempt['status'] != 'proposed':
                raise Problem('REPLAN_NOT_TRYABLE', '该 ReplanAttempt 当前不能执行 Try。', 409)
            attempt['status'] = transition_replan(attempt['status'], 'try')
            loaded = self._load_replan_context(replan_id)
            (_attempt, source, checkpoint, _state, task, resource, _raw, descriptor, _adapter,
             candidate_plan) = loaded
            outcome, _binding = self._try_outcome(_attempt, source, checkpoint, task, resource, descriptor,
                                                  candidate_plan)
            attempt['try_result_digest'] = digest(dumps(outcome).encode())
            if outcome['passed']:
                attempt['status'] = transition_replan(attempt['status'], 'try_passed')
                attempt['confirmation_binding_digest'] = outcome['binding_digest']
            else:
                attempt['status'] = transition_replan(attempt['status'], 'try_failed')
            validate_control('replan_attempt', attempt)
            self.store.put_replan_attempt(db, attempt)
            return {'replan_id': attempt['id'], 'status': attempt['status'],
                    'try_result_digest': attempt['try_result_digest'],
                    'confirmation_binding_digest': attempt['confirmation_binding_digest']}

        return self.idempotent('replan-try:' + replan_id, key, body, attempt_try)

    def confirm_replan(self, replan_id, body, key):
        if not isinstance(body, dict) or body:
            raise Problem('VALIDATION_ERROR', 'Confirm 不接受调用方参数。', 422)

        # Expire a pending confirmation before entering the idempotent creation
        # transaction if any of the Try-bound inputs drifted.  The source Run and
        # checkpoint remain untouched; a user may later create a fresh Attempt.
        pending = self.store.replan_attempt(replan_id)
        if pending['status'] == 'awaiting_confirmation':
            try:
                loaded = self._load_replan_context(replan_id)
                (_attempt, source, checkpoint, _state, task, resource, _raw, descriptor, _adapter,
                 candidate_plan) = loaded
                outcome, _binding = self._try_outcome(_attempt, source, checkpoint, task, resource, descriptor,
                                                      candidate_plan)
                if (not outcome['passed'] or digest(dumps(outcome).encode()) != pending['try_result_digest']
                        or outcome['binding_digest'] != pending['confirmation_binding_digest']):
                    raise Problem('REPLAN_CONFIRMATION_STALE', 'Try 的确认摘要已经失效。', 409)
            except Problem:
                with self.store.transaction() as db:
                    current = self.store.replan_attempt(replan_id)
                    if current['status'] == 'awaiting_confirmation':
                        current['status'] = transition_replan(current['status'], 'expire')
                        self.store.put_replan_attempt(db, current)
                raise Problem('REPLAN_CONFIRMATION_STALE', 'Try 的确认摘要已经失效；请重新创建方案。', 409) from None

        def attempt_confirm(db):
            attempt = self.store.replan_attempt(replan_id)
            if attempt['status'] == 'confirmed':
                return {'replan_id': attempt['id'], 'status': 'confirmed', 'run_id': attempt['confirmed_run_id']}
            if attempt['status'] != 'awaiting_confirmation':
                raise Problem('REPLAN_NOT_CONFIRMABLE', '只有通过 Try 的 ReplanAttempt 可以 Confirm。', 409)
            loaded = self._load_replan_context(replan_id)
            (_attempt, source, checkpoint, _state, task, resource, _raw, descriptor, _adapter,
             candidate_plan) = loaded
            outcome, _binding = self._try_outcome(_attempt, source, checkpoint, task, resource, descriptor,
                                                  candidate_plan)
            if (not outcome['passed'] or digest(dumps(outcome).encode()) != attempt['try_result_digest']
                    or outcome['binding_digest'] != attempt['confirmation_binding_digest']):
                raise Problem('REPLAN_CONFIRMATION_STALE', 'Try 的确认摘要已经失效；请重新创建方案。', 409)
            existing = next((run for run in self.store.listing('runs')
                             if run.get('restored_from_checkpoint_id') == checkpoint['id']), None)
            if existing:
                raise Problem('REPLAN_ALREADY_MATERIALIZED', '该 Checkpoint 已经创建过恢复 Run。', 409)
            run = self.new_run(db, task, source['id'], checkpoint['id'], checkpoint['remaining_limits'],
                               candidate_plan['id'], attempt['id'])
            attempt['status'] = transition_replan(attempt['status'], 'confirm')
            attempt['confirmed_run_id'] = run['id']
            validate_control('replan_attempt', attempt)
            self.store.put_replan_attempt(db, attempt)
            return {'replan_id': attempt['id'], 'status': 'confirmed', 'run_id': run['id']}

        return self.idempotent('replan-confirm:' + replan_id, key, body, attempt_confirm)

    def cancel_replan(self, replan_id, body, key):
        if not isinstance(body, dict) or body:
            raise Problem('VALIDATION_ERROR', 'Cancel 不接受调用方参数。', 422)

        def attempt_cancel(db):
            attempt = self.store.replan_attempt(replan_id)
            if attempt['status'] == 'cancelled':
                return {'replan_id': attempt['id'], 'status': 'cancelled'}
            if attempt['status'] in {'confirmed', 'rejected', 'expired'}:
                raise Problem('REPLAN_TERMINAL', '终态 ReplanAttempt 不能取消。', 409)
            attempt['status'] = transition_replan(attempt['status'], 'cancel')
            validate_control('replan_attempt', attempt)
            self.store.put_replan_attempt(db, attempt)
            return {'replan_id': attempt['id'], 'status': 'cancelled'}

        return self.idempotent('replan-cancel:' + replan_id, key, body, attempt_cancel)

    def restore(self, source_run_id, body, key):
        if not isinstance(body, dict) or body:
            raise Problem('VALIDATION_ERROR', '从 Checkpoint 恢复不接受请求参数。', 422)

        def create(db):
            source, checkpoint, _state, task, _resource, _raw, _descriptor, _adapter = self.load_restorable_checkpoint(source_run_id)
            existing = next((run for run in self.store.listing('runs')
                             if run.get('restored_from_checkpoint_id') == checkpoint['id']), None)
            if existing:
                return {'run_id': existing['id'], 'source_run_id': source['id'],
                        'checkpoint_id': checkpoint['id'], 'status': existing['status']}
            run = self.new_run(db, task, source['id'], checkpoint['id'], checkpoint['remaining_limits'],
                               source.get('plan_revision_id'))
            return {'run_id': run['id'], 'source_run_id': source['id'], 'checkpoint_id': checkpoint['id'], 'status': 'queued'}

        return self.idempotent('restore:' + source_run_id, key, body, create)

    def restore_status(self, source_run_id):
        """Read-only eligibility projection for the local workbench; never creates a Run."""
        try:
            _source, checkpoint, _state, _task, _resource, _raw, _descriptor, _adapter = self.load_restorable_checkpoint(source_run_id)
        except Problem as exc:
            return {'eligible': False, 'checkpoint_id': None, 'reason_code': exc.code}
        return {'eligible': True, 'checkpoint_id': checkpoint['id'], 'reason_code': None}

    def execute(self, run_id):
        engine = self.store.get('runs', run_id)['selected_engine']
        if engine == 'engine_local_research_demo':
            return self.research.execute(run_id)
        if engine == 'engine_research_multi_agent_simulation':
            return self.research_agents.execute(run_id)
        if engine == 'engine_claude_research_native':
            return self.research_native.execute(run_id)
        adapter = None
        try:
            with self.store.transaction() as db:
                run = self.store.get('runs', run_id)
                if run['status'] != 'queued':
                    return
                self.check(run_id)
                run['status'] = 'running'
                self.store.event(db, run, 'run.started')
            adapter = self.adapters.get(run['selected_engine'])
            if adapter is None:
                raise Problem('ENGINE_UNAVAILABLE', '运行绑定引擎不可用。')
            accepted = self.store.events(run_id)[0]['data'].get('adapter_digest')
            if accepted and accepted != digest(dumps(adapter.describe()).encode()):
                raise Problem('ADAPTER_VERSION_MISMATCH', '排队后适配器版本发生变化。')
            task = self.store.get('tasks', run['task_id'])
            resource = self.store.get('resources', task['context']['resource_ids'][0])
            raw = self.store.raw(resource['id'])
            if digest(raw) != resource['sha256']:
                raise Problem('RESOURCE_INTEGRITY_ERROR', '资源摘要校验失败。')
            request = AdapterRequest(copy.deepcopy(task), copy.deepcopy(run), copy.deepcopy(resource), raw)
            restored_from = run.get('restored_from_checkpoint_id')
            if restored_from:
                source, checkpoint, state, source_task, source_resource, source_raw, source_descriptor, source_adapter = self.load_restorable_checkpoint(run['based_on_run_id'])
                if (checkpoint['id'] != restored_from or source_task['id'] != task['id']
                        or source_resource['id'] != resource['id'] or source_raw != raw
                        or source_adapter is not adapter or source_descriptor != adapter.describe()):
                    raise Problem('CHECKPOINT_INCOMPATIBLE', '恢复 Run 与原 Checkpoint 的绑定不匹配。')
                replan_attempt_id = run.get('replan_attempt_id')
                if replan_attempt_id:
                    attempt, replan_source, replan_checkpoint, _state, replan_task, replan_resource, _raw, replan_descriptor, _adapter, candidate_plan = self._load_replan_context(replan_attempt_id)
                    outcome, _binding = self._try_outcome(attempt, replan_source, replan_checkpoint, replan_task,
                                                          replan_resource, replan_descriptor, candidate_plan)
                    if (attempt['status'] != 'confirmed' or attempt['confirmed_run_id'] != run_id
                            or candidate_plan['id'] != run.get('plan_revision_id')
                            or not outcome['passed']
                            or outcome['binding_digest'] != attempt['confirmation_binding_digest']):
                        raise Problem('REPLAN_BINDING_INCOMPATIBLE', '确认后的 Replan 绑定已失效。', 409)
                proposed = adapter.restore_run(request, state)
                with self.store.transaction() as db:
                    self.check(run_id)
                    current = self.store.get('runs', run_id)
                    self.store.event(db, current, 'checkpoint.restored', {
                        'checkpoint_id': checkpoint['id'], 'checkpoint_sha256': checkpoint['sha256'],
                        'source_run_id': source['id'],
                    })
                    if replan_attempt_id:
                        self.store.event(db, current, 'checkpoint.verified', {
                            'replan_attempt_id': replan_attempt_id, 'checkpoint_id': checkpoint['id'],
                            'plan_revision_id': run['plan_revision_id'], 'mode': 'deterministic_replan',
                        })
                        self.store.event(db, current, 'plan.revision.activated', {
                            'replan_attempt_id': replan_attempt_id, 'plan_revision_id': run['plan_revision_id'],
                            'start_node_id': 'node_checkpointverify',
                        })
            else:
                resource_step_id = None

                def emit(kind, data):
                    nonlocal resource_step_id
                    validate_event(kind, data)
                    resource_step_id = self.stage(run_id, data['tool'])

                proposed = adapter.start_run(request, emit, lambda: self.check(run_id))
                if resource_step_id is None:
                    raise Problem('ADAPTER_PROTOCOL_ERROR', '适配器没有提交固定资源检查步骤。')
                self.create_checkpoint(run_id, task, resource, adapter.describe(), request, adapter, proposed, resource_step_id)
            validate_result(proposed)
            result = proposed.metrics
            # Cleanup must succeed before a successful terminal result is committed.
            try:
                adapter.cleanup(run_id)
            except Exception:
                raise Problem('CLEANUP_FAILED', '适配器清理未确认完成。') from None
            adapter = None
            try:
                outputs = artifacts(resource, result, task['objective'], run_id)
            except Exception:
                # This is the sole causal branch ADR-0019 may replan.  It occurs after
                # the immutable statistics checkpoint and before any artifact is stored.
                raise Problem('ARTIFACT_PUBLICATION_FAILED', '受控产物构建失败，可创建固定 Replan 方案。') from None
            # Recompute the full fixed result before publication; restoration never falls
            # back to a new analysis result if its saved state differs.
            expected = analyze(raw, lambda: self.check(run_id))
            if dumps(result) != dumps(expected):
                code = 'CHECKPOINT_STATE_INVALID' if restored_from else 'VALIDATION_FAILED'
                raise Problem(code, '固定统计状态与输入资源的独立回算不一致。')
            # Independently recompute numeric totals with math.fsum rather than trusting adapter output.
            headers, rows, _ = parse_csv(raw)
            for index, column in enumerate(result['columns']):
                self.check(run_id)
                if column['type'] == 'number':
                    expected = math.fsum(float(row[index]) for row in rows if row[index].strip())
                    if not math.isclose(column['sum'], expected, rel_tol=1e-12, abs_tol=1e-9):
                        raise Problem('VALIDATION_FAILED', '数值独立回算失败。')
            with self.store.transaction() as db:
                self.check(run_id)
                run = self.store.get('runs', run_id)
                if run.get('consumed_turns', 0) + 2 > run['effective_limits']['max_turns']:
                    raise Problem('BUDGET_EXCEEDED', '运行剩余工具步骤预算不足以发布产物。')
                run['consumed_turns'] = run.get('consumed_turns', 0) + 2
                step_id = uid('step')
                self.store.event(db, run, 'run.result.proposed', {'row_count': result['row_count']})
                for name, media, body in outputs:
                    artifact = {'id': uid('art'), 'run_id': run_id, 'step_id': step_id, 'name': name,
                                'media_type': media, 'size_bytes': len(body), 'sha256': digest(body),
                                'data_class': resource['data_class'], 'validation_status': 'passed', 'created_at': now()}
                    validate('artifact', artifact)
                    db.execute('INSERT INTO artifacts VALUES(?,?,?,?)', (artifact['id'], run_id, dumps(artifact), body))
                    self.store.event(db, run, 'artifact.published', {'artifact_id': artifact['id'], 'name': name}, step_id)
                self.store.event(db, run, 'tool.call.completed', {'tool': 'artifact.publish'}, step_id)
                self.store.event(db, run, 'artifact.validation.completed', {'checks': ['input_sha256', 'numeric_recalculation', 'artifact_schema'], 'status': 'passed'}, step_id)
                self.store.event(db, run, 'tool.call.completed', {'tool': 'run.final_answer'}, uid('step'))
                if run.get('restored_from_checkpoint_id') and run.get('based_on_run_id'):
                    for gap in self.store.gaps_for_run(run['based_on_run_id']):
                        if gap['status'] == 'open' and self._gap_shape_is_compatible(gap, run['based_on_run_id']):
                            gap['status'] = 'resolved'
                            validate_control('gap', gap)
                            self.store.update_gap(db, gap)
                            self.store.event(db, run, 'gap.resolved', {
                                'gap_id': gap['id'], 'source_run_id': run['based_on_run_id'],
                                'resolution_action_id': 'artifact.publish',
                            })
                run['status'], run['exit_reason'] = 'succeeded', 'COMPLETED'
                self.store.event(db, run, 'run.succeeded', {'usage': {'model_calls': 0, 'cost_minor': 0}})
        except Exception as exc:
            cleanup_failed = False
            if adapter is not None:
                try:
                    adapter.cleanup(run_id)
                except Exception:
                    cleanup_failed = True
            with self.store.transaction() as db:
                run = self.store.get('runs', run_id)
                if cleanup_failed:
                    self.store.event(db, run, 'adapter.cleanup.failed', {'error_code': 'CLEANUP_FAILED'})
                if run['status'] in TERMINAL:
                    return
                code = 'CLEANUP_FAILED' if cleanup_failed else (exc.code if isinstance(exc, Problem) else 'INTERNAL_ERROR')
                run['status'] = 'expired' if run['status'] == 'queued' and code == 'TIMEOUT' else 'failed'
                run['exit_reason'] = code
                failure_event = self.store.event(db, run, 'run.' + run['status'], {'error_code': code})
                if code == 'ARTIFACT_PUBLICATION_FAILED':
                    self._artifact_failure_gap(db, run, failure_event)

    def recover(self):
        self.research.recover()
        self.research_agents.recover()
        self.research_native.recover()
        with self.store.transaction() as db:
            for run in self.store.listing('runs'):
                if run['status'] == 'running':
                    run['status'], run['exit_reason'] = 'failed', 'SERVER_RESTARTED'
                    self.store.event(db, run, 'run.failed', {'error_code': 'SERVER_RESTARTED'})

    def start(self):
        self.recover()
        def loop():
            while not self.stopping.wait(.15):
                for run in reversed(self.store.listing('runs')):
                    if self.stopping.is_set():
                        return
                    if run['status'] == 'queued' and not run.get('parent_run_id'):
                        self.execute(run['id'])
        self.thread = threading.Thread(target=loop, name='local-worker', daemon=True)
        self.thread.start()

    def stop(self):
        self.stopping.set()
        if self.thread:
            self.thread.join()
