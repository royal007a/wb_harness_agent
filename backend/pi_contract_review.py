"""Product Run wrapper for the offline Pi contract-review adapter."""
from __future__ import annotations

import copy
import json
from pathlib import Path

from jsonschema import Draft202012Validator

from adapters.contracts import AdapterRequest
from adapters.pi_contract_review import PiContractReviewAdapter
from .analysis import Problem, digest
from .service import DENY, ROOT, TERMINAL, validate
from .store import dumps, now, uid


ENGINE = 'engine_pi_contract_review_offline'
RUNTIME = 'pi_contract_review_offline@1'
SCHEMA = json.loads((ROOT / 'specs/v1/pi-contract-review-runtime.schema.json').read_text())
REVIEW_SCHEMA = json.loads((ROOT / 'specs/v1/pi-contract-review.schema.json').read_text())


class PiContractReviewRuns:
    def __init__(self, service):
        self.service = service
        self.store = service.store
        self.adapter = PiContractReviewAdapter()

    @staticmethod
    def _validate(kind, value):
        errors = list(Draft202012Validator({'$ref': '#/$defs/' + kind, '$defs': SCHEMA['$defs']}).iter_errors(value))
        if errors:
            raise Problem('VALIDATION_ERROR', 'Pi 合同审查请求不满足机器契约。', 422)

    def create(self, body, key):
        self._validate('request', body)
        resource = self.store.get('resources', body['resource_id'])
        if resource['data_class'] != 'Public' or not resource['name'].lower().endswith('.pdf'):
            raise Problem('PDF_RESOURCE_INVALID', 'Pi 离线合同审查只接受已登记 Public PDF。', 422)
        if not self.store.raw(resource['id']).startswith(b'%PDF-'):
            raise Problem('PDF_RESOURCE_INVALID', '输入资源不是有效 PDF。', 422)

        def create(db):
            task = {
                'id': uid('task'), 'project_id': 'prj_local', 'objective': body['objective'],
                'agent_spec_version': RUNTIME,
                'context': {'resource_ids': [resource['id']], 'variables': {'request': copy.deepcopy(body)}},
                'engine_policy': {'mode': 'explicit', 'engine_id': ENGINE,
                                  'required_capabilities': ['actions.tool_call', 'output.structured', 'control.cancel']},
                'model_policy': {'text_and_code': 'faux:offline-contract-review', 'vision': None, 'allow_fallback': False},
                'requested_permissions': {'profile': 'analysis_read_only', 'profile_version': 1,
                                          'allow_tools': ['evidence.locate'], 'deny_capabilities': list(DENY)},
                'limits': {'max_turns': 4, 'timeout_seconds': body['timeout_seconds'],
                           'max_input_tokens': 4096, 'max_cost_minor': 0}, 'created_at': now(),
            }
            validate('task', task)
            db.execute('INSERT INTO tasks VALUES(?,?)', (task['id'], dumps(task)))
            run = self.new_run(db, task)
            return {'task': task, 'initial_run': run}

        return self.service.idempotent('pi-contract-review', key, body, create)

    def new_run(self, db, task, based_on=None):
        policy = {'profile_id': 'analysis_read_only', 'profile_version': 1,
                  'allowed_tools': ['evidence.locate'], 'denied_capabilities': list(DENY),
                  'decision_digest': digest(dumps(task['requested_permissions']).encode())}
        run = {'id': uid('run'), 'task_id': task['id'], 'status': 'queued', 'selected_engine': ENGINE,
               'selected_models': {'text_and_code': 'faux:offline-contract-review'},
               'effective_permissions': policy, 'effective_limits': copy.deepcopy(task['limits']),
               'attempt_number': 1, 'based_on_run_id': based_on, 'latest_sequence': 0,
               'exit_reason': None, 'created_at': now(), 'updated_at': now()}
        validate('run', run)
        db.execute('INSERT INTO runs VALUES(?,?,?)', (run['id'], task['id'], dumps(run)))
        self.store.event(db, run, 'run.queued', {'engine': ENGINE, 'adapter': self.adapter.describe(),
                                                  'adapter_digest': digest(dumps(self.adapter.describe()).encode()),
                                                  'mode': 'offline_faux'})
        return run

    def detail(self, run_id):
        run = self.store.get('runs', run_id)
        if run['selected_engine'] != ENGINE:
            raise Problem('NOT_FOUND', 'Pi 合同审查 Run 不存在。', 404)
        return {'run': run, 'task': self.store.get('tasks', run['task_id']),
                'artifacts': self.store.artifact_list(run_id), 'mode': RUNTIME,
                'runtime_enabled': False, 'external_calls': 0,
                'gate_required': run['status'] == 'waiting_approval'}

    def _publish(self, db, run, name, value, media='application/json'):
        body = value.encode() if isinstance(value, str) else dumps(value).encode()
        if len(body) > 65536:
            raise Problem('OUTPUT_LIMIT', 'Pi 合同审查产物超过 64 KiB。', 422)
        artifact = {'id': uid('art'), 'run_id': run['id'], 'step_id': uid('step'), 'name': name,
                    'media_type': media, 'size_bytes': len(body), 'sha256': digest(body),
                    'data_class': 'Public', 'validation_status': 'passed', 'created_at': now()}
        validate('artifact', artifact)
        db.execute('INSERT INTO artifacts VALUES(?,?,?,?)', (artifact['id'], run['id'], dumps(artifact), body))
        self.store.event(db, run, 'artifact.published', {'artifact_id': artifact['id'], 'name': name}, artifact['step_id'])
        return artifact

    def execute(self, run_id):
        try:
            with self.store.transaction() as db:
                run = self.store.get('runs', run_id)
                if run['selected_engine'] != ENGINE or run['status'] != 'queued':
                    return
                self.service.check(run_id)
                run['status'] = 'running'
                self.store.event(db, run, 'run.started', {'mode': RUNTIME, 'external_calls': 0})
            task = self.store.get('tasks', run['task_id'])
            resource = self.store.get('resources', task['context']['resource_ids'][0])
            events = []

            def emit(kind, payload):
                events.append((kind, payload))
                with self.store.transaction() as db:
                    current = self.store.get('runs', run_id)
                    self.store.event(db, current, 'pi.' + kind.replace('.', '_'), {'payload': payload})

            result = self.adapter.start_run(AdapterRequest(task, run, resource, self.store.raw(resource['id'])), emit,
                                            lambda: self.service.check(run_id))
            with self.store.transaction() as db:
                current = self.store.get('runs', run_id)
                artifact = self._publish(db, current, 'pi-contract-review.json', result.finding)
                evidence = result.finding['evidence_refs']
                handoff = {
                    'schema_version': 'pi-contract-review-handoff@1',
                    'requirements': [
                        'R1：每个高风险结论必须绑定当前 Public PDF 的 Evidence 引用',
                        'R2：人工确认前不得将结果标记为正式交付',
                    ],
                    'gate': {'reviewer': 'human', 'checks': ['核对 Evidence 页码与原始 PDF', '确认风险建议是否可接受'],
                             'on_reject': '保留审计记录并退回审查 Run'},
                    'summary': 'Pi 离线合同审查候选结果，等待人工 Gate',
                    'decisions': [], 'evidence': evidence,
                    'remaining': ['人工确认高风险条款'],
                    'risks': ['Faux Provider 结果不代表法律意见'],
                    'next_action': '请人工 Reviewer 核对引用后执行 Gate pass 或 reject',
                }
                handoff_errors = list(Draft202012Validator(
                    {'$ref': '#/$defs/handoff', '$defs': REVIEW_SCHEMA['$defs']}
                ).iter_errors(handoff))
                if handoff_errors:
                    raise Problem('HANDOFF_INVALID', 'Pi Task Handoff 不满足机器契约。', 409)
                handoff_artifact = self._publish(db, current, 'pi-contract-review-handoff.json', handoff)
                self.store.event(db, current, 'evidence.proposed', {
                    'artifact_id': artifact['id'], 'handoff_artifact_id': handoff_artifact['id'], 'evidence_refs': evidence,
                    'source_resource_id': resource['id'], 'source_sha256': resource['sha256'],
                }, artifact['step_id'])
                self.store.event(db, current, 'run.result.proposed', {
                    'artifact_id': artifact['id'], 'status': 'needs_human', 'risk_level': 'high',
                    'external_calls': 0, 'model_calls': 0,
                }, artifact['step_id'])
                current['status'], current['exit_reason'] = 'waiting_approval', 'GATE_REQUIRED'
                self.store.event(db, current, 'gate.awaiting_human', {'artifact_id': artifact['id'],
                                                                        'handoff_artifact_id': handoff_artifact['id'],
                                                                        'decision_options': ['pass', 'reject']})
        except Exception as exc:
            with self.store.transaction() as db:
                run = self.store.get('runs', run_id)
                if run['status'] not in TERMINAL:
                    run['status'], run['exit_reason'] = 'failed', getattr(exc, 'code', 'PI_RUNTIME_ERROR')
                    self.store.event(db, run, 'run.failed', {'error_code': run['exit_reason']})

    def gate(self, run_id, body, key):
        self._validate('gate_decision', body)
        run = self.store.get('runs', run_id)
        if run['selected_engine'] != ENGINE or run['status'] != 'waiting_approval':
            raise Problem('GATE_NOT_OPEN', 'Pi Run 当前没有可处理的人工 Gate。', 409)

        def decide(db):
            current = self.store.get('runs', run_id)
            handoffs = [item for item in self.store.artifact_list(run_id) if item['name'] == 'pi-contract-review-handoff.json']
            if not handoffs:
                raise Problem('HANDOFF_MISSING', 'Gate 前必须存在可审计的 Pi Task Handoff。', 409)
            status = 'succeeded' if body['decision'] == 'pass' else 'failed'
            reason = 'GATE_PASSED' if status == 'succeeded' else 'GATE_REJECTED'
            current['status'], current['exit_reason'] = status, reason
            self.store.event(db, current, 'gate.decision', {'decision': body['decision'], 'reason': body['reason'],
                                                            'handoff_artifact_id': handoffs[-1]['id']})
            self.store.event(db, current, 'run.' + status, {'exit_reason': reason, 'handoff_required': True})
            return current

        return self.service.idempotent('pi-contract-review:gate:' + run_id, key, body, decide)

    def cancel(self, run_id):
        with self.store.transaction() as db:
            run = self.store.get('runs', run_id)
            if run['selected_engine'] != ENGINE:
                raise Problem('NOT_FOUND', 'Pi 合同审查 Run 不存在。', 404)
            if run['status'] not in TERMINAL:
                run['status'], run['exit_reason'] = 'cancelled', 'USER_CANCELLED'
                self.store.event(db, run, 'run.cancelled', {'external_calls': 0})
            return run

    def recover(self):
        for run in self.store.listing('runs'):
            if run['selected_engine'] == ENGINE and run['status'] == 'running':
                self.cancel(run['id'])
