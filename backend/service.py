"""Control-plane policy, idempotency and bounded worker lifecycle."""
import json
import threading
import math
import copy
from datetime import datetime
from pathlib import Path

from jsonschema import Draft202012Validator, FormatChecker

from .analysis import Problem, artifacts, digest, parse_csv
from adapters.contracts import AdapterRequest, validate_event, validate_result
from adapters.local import LocalAnalyticsAdapter
from .store import dumps, now, uid

ROOT = Path(__file__).resolve().parents[1]
BUNDLE = json.loads((ROOT / 'specs/v1/core-contracts.schema.json').read_text())
TOOLS = ('resource.inspect', 'artifact.publish', 'run.final_answer')
DENY = ('network', 'package_install', 'external_write', 'host_path', 'secret')
TERMINAL = {'succeeded', 'failed', 'cancelled', 'expired'}


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
        from .research import Research
        self.research = Research(self)

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

    def new_run(self, db, task, based_on=None):
        if task['engine_policy']['engine_id'] == 'engine_local_research_demo':
            return self.research.new_run(db, task, based_on)
        active = [r for r in self.store.listing('runs') if r['status'] not in TERMINAL]
        if len(active) >= 32:
            raise Problem('RATE_LIMITED', '本地待执行队列已满（32）。', 429)
        attempts = [r for r in self.store.listing('runs') if r['task_id'] == task['id']]
        policy = {'profile_id': 'analysis_read_only', 'profile_version': 1, 'allowed_tools': list(TOOLS),
                  'denied_capabilities': list(DENY), 'decision_digest': digest(dumps(task['requested_permissions']).encode())}
        run = {'id': uid('run'), 'task_id': task['id'], 'status': 'queued', 'selected_engine': 'engine_mock_analytics',
               'selected_models': {}, 'effective_permissions': policy, 'effective_limits': task['limits'],
               'attempt_number': len(attempts) + 1, 'based_on_run_id': based_on, 'latest_sequence': 0,
               'exit_reason': None, 'created_at': now(), 'updated_at': now()}
        validate('run', run)
        db.execute('INSERT INTO runs VALUES(?,?,?)', (run['id'], task['id'], dumps(run)))
        descriptor = self.adapters[run['selected_engine']].describe()
        validate('adapter_description', descriptor)
        self.store.event(db, run, 'run.queued', {'engine': run['selected_engine'], 'adapter': descriptor,
                                               'adapter_digest': digest(dumps(descriptor).encode())})
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
        if self.store.get('runs', run_id)['selected_engine'] == 'engine_local_research_demo':
            return self.research.cancel(run_id)
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
            step_id = uid('step')
            self.store.event(db, run, 'tool.call.completed', {'tool': tool, 'implementation': 'deterministic'}, step_id)

    def execute(self, run_id):
        if self.store.get('runs', run_id)['selected_engine'] == 'engine_local_research_demo':
            return self.research.execute(run_id)
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
            def emit(kind, data):
                validate_event(kind, data)
                self.stage(run_id, data['tool'])
            proposed = adapter.start_run(AdapterRequest(copy.deepcopy(task), copy.deepcopy(run), copy.deepcopy(resource), raw),
                                         emit, lambda: self.check(run_id))
            validate_result(proposed)
            result = proposed.metrics
            # Cleanup must succeed before a successful terminal result is committed.
            try:
                adapter.cleanup(run_id)
            except Exception:
                raise Problem('CLEANUP_FAILED', '适配器清理未确认完成。') from None
            adapter = None
            outputs = artifacts(resource, result, task['objective'], run_id)
            # Independently recompute totals with math.fsum rather than trusting adapter output.
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
                self.store.event(db, run, 'run.' + run['status'], {'error_code': code})

    def recover(self):
        self.research.recover()
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
