"""DSH Product Run orchestration; platform owns policy, credentials, budget and publication."""
from __future__ import annotations
import asyncio
import copy
import json
import os
from pathlib import Path
import re
import subprocess
import time
from jsonschema import Draft202012Validator

from adapters.dsh import DshAdapter
from adapters.dsh_workspace import cleanup_workspaces
from .agent_runtime import KeyringCredentialResolver, reject_sensitive
from .adaptive_retrieval import build_parent_child_chunks
from .analysis import Problem, digest
from .business_budget import BusinessTokenLedger, budgeted_model_call
from .dsh_provider import MODEL, BASE, TOOL_NAMES, provider_payload, send_real, send_probe
from .service import ROOT, DENY, TERMINAL, validate
from .store import dumps, uid, now

ENGINE = 'engine_dsh_document'
SCHEMA = json.loads((ROOT / 'specs/v1/dsh-runtime.schema.json').read_text())


def validate_dsh(kind, value):
    validator = Draft202012Validator({'$ref': '#/$defs/' + kind, '$defs': SCHEMA['$defs']})
    if list(validator.iter_errors(value)):
        raise Problem('DSH_VALIDATION_ERROR', 'DSH 数据不满足契约。', 422)


class DshRuntime:
    def __init__(self, service):
        self.service, self.store = service, service.store
        self.ledger = BusinessTokenLedger(self.store)
        self.adapter = DshAdapter()
        self.send_probe = send_probe
        self.send_real = send_real
        self.credentials = KeyringCredentialResolver()
        self.release = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip()

    def status(self):
        available = (ROOT / 'dsh-adapter/node_modules/@deepseek-ai/dsh/lib/bin.js').is_file()
        return {'engine': ENGINE, 'runtime': 'deepseek-harness@0.2.1-alpha.1', 'release': self.release,
                'installed': available, 'integration_probe': available,
                'real_provider_enabled': os.getenv('HARNESS_DSH_REAL_ENABLED') == '1',
                'credential_ref_configured': bool(os.getenv('HARNESS_DSH_CREDENTIAL_REF')),
                'workspace_recovery': getattr(self, 'cleanup_status', None),
                'model': MODEL, 'base_url': BASE, 'tools': sorted(TOOL_NAMES),
                'shell_enabled': False, 'network_tools_enabled': False,
                'max_model_calls': 8, 'max_tool_calls': 16, 'max_token_limit': 20_000_000,
                'note': '联调模式使用合成 Provider；DSH 进程和工具循环为真实运行。真实 Provider 需要独立准入。'}

    def require_mode(self, mode):
        if not self.status()['installed']:
            raise Problem('DSH_DEPENDENCY_MISSING', '请安装固定 DSH 依赖。', 503)
        if mode == 'real_provider' and (os.getenv('HARNESS_DSH_REAL_ENABLED') != '1' or
                                       not os.getenv('HARNESS_DSH_CREDENTIAL_REF')):
            raise Problem('DSH_PROVIDER_NOT_ADMITTED', '真实 Provider 尚未准入或未配置密钥引用；不会回退联调模式。', 409)

    def create(self, body, key):
        validate_dsh('request', body)
        if not body['objective'].strip() or not body['document'].strip():
            raise Problem('DSH_VALIDATION_ERROR', '问题和文档不能为空。', 422)
        reject_sensitive(body['objective']); reject_sensitive(body['document'])
        self.require_mode(body['mode'])

        def create(db):
            if sum(r['status'] not in TERMINAL for r in self.store.listing('runs')) >= 8:
                raise Problem('RATE_LIMITED', 'DSH 待执行队列已满。', 429)
            raw = body['document'].encode()
            sha = digest(raw)
            resource = {'id': 'res_' + sha, 'name': 'dsh-document.txt', 'sha256': sha,
                        'size_bytes': len(raw), 'data_class': 'Public', 'row_count': 0,
                        'columns': [], 'encoding': 'utf-8', 'created_at': now()}
            db.execute('INSERT OR IGNORE INTO resources VALUES(?,?,?)', (resource['id'], dumps(resource), raw))
            task = {'id': uid('task'), 'project_id': 'prj_local', 'objective': body['objective'],
                'agent_spec_version': 'dsh_document@1',
                'context': {'resource_ids': [resource['id']], 'variables': {
                    'mode': body['mode'], 'token_limit': body.get('token_limit', 20000000 if body['mode'] == 'real_provider' else 200000),
                    'billing_mode': 'coding_plan_no_balance_fallback' if body['mode'] == 'real_provider' else 'synthetic',
                    'credential_ref': os.getenv('HARNESS_DSH_CREDENTIAL_REF') if body['mode'] == 'real_provider' else None}},
                'engine_policy': {'mode': 'explicit', 'engine_id': ENGINE,
                                  'required_capabilities': ['actions.tool_call', 'artifacts.files', 'control.cancel']},
                'model_policy': {'text_and_code': MODEL if body['mode'] == 'real_provider' else 'synthetic:dsh-integration-probe',
                                 'vision': None, 'allow_fallback': False},
                'requested_permissions': {'profile': 'analysis_read_only', 'profile_version': 1,
                                         'allow_tools': sorted(TOOL_NAMES), 'deny_capabilities': list(DENY)},
                'limits': {'max_turns': 8, 'timeout_seconds': body.get('timeout_seconds', 120),
                           'max_input_tokens': 64000, 'max_cost_minor': 0}, 'created_at': now()}
            validate('task', task)
            db.execute('INSERT INTO tasks VALUES(?,?)', (task['id'], dumps(task)))
            run = self.new_run(db, task)
            return {'task': task, 'initial_run': run}
        return self.service.idempotent('dsh-document', key, body, create)

    def new_run(self, db, task, based_on=None):
        self.require_mode(task['context']['variables']['mode'])
        if sum(r['status'] not in TERMINAL for r in self.store.listing('runs')) >= 8:
            raise Problem('RATE_LIMITED', 'DSH 待执行队列已满。', 429)
        permissions = {'profile_id': 'analysis_read_only', 'profile_version': 1,
            'allowed_tools': sorted(TOOL_NAMES), 'denied_capabilities': list(DENY),
            'decision_digest': digest(dumps(task['requested_permissions']).encode())}
        run = {'id': uid('run'), 'task_id': task['id'], 'status': 'queued', 'selected_engine': ENGINE,
               'selected_models': {'text_and_code': task['model_policy']['text_and_code']},
               'effective_permissions': permissions, 'effective_limits': copy.deepcopy(task['limits']),
               'attempt_number': 1 + sum(r['task_id'] == task['id'] for r in self.store.listing('runs')),
               'based_on_run_id': based_on, 'latest_sequence': 0, 'exit_reason': None,
               'created_at': now(), 'updated_at': now()}
        validate('run', run)
        db.execute('INSERT INTO runs VALUES(?,?,?)', (run['id'], task['id'], dumps(run)))
        self.store.event(db, run, 'run.queued', {'engine': ENGINE, 'mode': task['context']['variables']['mode']})
        return run

    def detail(self, ident):
        with self.store.lock:
            run = self.store.get('runs', ident)
            if run['selected_engine'] != ENGINE:
                raise Problem('NOT_FOUND', 'DSH Run 不存在。', 404)
            task = self.store.get('tasks', run['task_id'])
            row = self.store.db.execute('SELECT 1 FROM business_budget_roots WHERE id=?', (ident,)).fetchone()
            return {'run': run, 'task': task, 'artifacts': self.store.artifact_list(ident),
                    'budget': self.ledger.snapshot(ident) if row else None,
                    'mode': task['context']['variables']['mode']}

    def cancel(self, ident):
        with self.store.transaction() as db:
            run = self.detail(ident)['run']
            if run['status'] not in TERMINAL:
                run['status'], run['exit_reason'] = 'cancelled', 'USER_CANCELLED'
                self.store.event(db, run, 'run.cancelled')
                db.execute("UPDATE business_budget_roots SET status='cancelled' WHERE id=? AND status='active'", (ident,))
            return run

    def execute(self, ident):
        try:
            with self.store.transaction() as db:
                run = self.detail(ident)['run']
                if run['status'] != 'queued':
                    return
                self.service.check(ident)
                run['status'] = 'running'
                self.store.event(db, run, 'run.started', {'runtime': 'deepseek-harness@0.2.1-alpha.1'})
            task = self.store.get('tasks', run['task_id'])
            settings = task['context']['variables']
            self.require_mode(settings['mode'])
            binding = digest(dumps({'model': task['model_policy'], 'settings': settings}).encode())
            self.ledger.register_root(ident, binding, settings['token_limit'])
            document = self.store.raw(task['context']['resource_ids'][0]).decode()
            chunks = build_parent_child_chunks(document, max_child_chars=1500, parent_max_chars=3000)
            clauses = {f'clause-{i+1}': chunk['text'] for i, chunk in enumerate(chunks['children'])}
            counts = {'model_calls': 0, 'tool_calls': 0}
            seen_clauses = set()
            deadline = time.monotonic() + task['limits']['timeout_seconds']
            def check():
                self.service.check(ident)
                if time.monotonic() >= deadline:
                    raise Problem('TIMEOUT', 'DSH 已到截止时间。', 409)
            def event(kind, value):
                with self.store.transaction() as db:
                    check()
                    self.store.event(db, self.store.get('runs', ident), kind, value)
            def emit(value):
                validate_dsh('observation', value)
                event('dsh.observation', value)
            def model_call(request):
                check()
                if counts['model_calls'] >= 8:
                    raise Problem('DSH_MODEL_CALL_LIMIT', '达到 8 次模型调用上限。', 409)
                payload = provider_payload(request)
                counts['model_calls'] += 1
                async def send(value, limit):
                    check()
                    if settings['mode'] == 'integration_probe':
                        return await self.send_probe(value, limit)
                    credential = self.credentials.resolve(settings['credential_ref'])
                    return await self.send_real(value, limit, credential)
                async def controlled_call():
                    cancel = asyncio.Event()
                    async def watch():
                        while True:
                            await asyncio.sleep(.05)
                            try:
                                check()
                            except Problem:
                                cancel.set()
                                return
                    watcher = asyncio.create_task(watch())
                    try:
                        return await budgeted_model_call(self.ledger, member_id=ident,
                            call_id=f'call_{counts["model_calls"]}', binding_digest=binding, payload=payload,
                            # Reserve the documented *entire* model input/output capacity.
                            # Not a tokenizer estimate; intentionally very conservative.
                            input_counter=lambda p: 1024000 if settings['mode'] == 'real_provider' else len(dumps(p).encode()) + 4096,
                            output_limit=256000 if settings['mode'] == 'real_provider' else 2048,
                            send=send, timeout_seconds=min(45, max(.1, deadline-time.monotonic())), cancel_event=cancel)
                    except asyncio.CancelledError:
                        check()
                        raise Problem('DSH_CANCELLED', 'DSH 已取消。', 409) from None
                    finally:
                        watcher.cancel()
                        await asyncio.gather(watcher, return_exceptions=True)
                result = asyncio.run(controlled_call())
                check()
                event('dsh.model.completed', {'call_number': counts['model_calls'],
                    'mode': settings['mode'], 'usage': result['usage']})
                return result
            def tool_call(body):
                check()
                if not isinstance(body, dict) or set(body) != {'name', 'arguments'} or body['name'] not in TOOL_NAMES:
                    raise Problem('DSH_TOOL_POLICY', '工具未准入。', 403)
                if counts['tool_calls'] >= 16:
                    raise Problem('DSH_TOOL_LIMIT', '达到工具上限。', 409)
                args = body['arguments']
                expected = 'clause_id' if body['name'] == 'read_clause' else 'query'
                if (not isinstance(args, dict) or set(args) != {expected} or
                    not isinstance(args[expected], str) or not 1 <= len(args[expected]) <= 200):
                    raise Problem('DSH_TOOL_INPUT', '工具参数无效。', 422)
                if expected == 'clause_id':
                    if args[expected] not in clauses:
                        raise Problem('DSH_CLAUSE_NOT_FOUND', '条款不存在。', 404)
                    selected = [args[expected]]
                else:
                    query = args[expected].casefold()
                    selected = [key for key, text in clauses.items() if query in text.casefold()][:3]
                counts['tool_calls'] += 1
                seen_clauses.update(selected)
                event('dsh.tool.completed', {'tool': body['name'], 'call_number': counts['tool_calls'],
                    'clause_ids': selected, 'arguments_sha256': digest(dumps(args).encode())})
                return {'text': dumps([{'clause_id': key, 'text': clauses[key]} for key in selected])}
            prompt = (f'平台文档已登记为 {len(clauses)} 个证据块，ID 范围 clause-1 到 clause-{len(clauses)}。'
                      'ID 是平台证据块编号，不等于合同原文条号。search_document 是字面子串检索，不支持正则。\n'
                      + task['objective'])
            result = self.adapter.run(prompt,
                Path(os.getenv('HARNESS_DSH_RUN_ROOT', ROOT / '.local/dsh-runs')), MODEL,
                model_call, tool_call, emit, check)
            validate_dsh('result', result)
            cited = set(re.findall(r'clause-[0-9]+', result['text']))
            if not counts['model_calls'] or not seen_clauses:
                raise Problem('DSH_EVIDENCE_NOT_READ', '没有读取文档证据，拒绝发布。', 409)
            if not cited or not cited <= seen_clauses:
                raise Problem('DSH_EVIDENCE_CITATION_INVALID', '引用必须指向本轮实际读取的证据块。', 409)
            with self.store.transaction() as db:
                check()
                current = self.store.get('runs', ident)
                artifact = self.service.pi_contract_review._publish(db, current, 'dsh-analysis.txt', result['text'], 'text/plain')
                current['status'], current['exit_reason'] = 'succeeded', 'COMPLETED'
                self.store.event(db, current, 'run.succeeded', {'artifact_id': artifact['id'], **counts,
                    'session_sha256': result['session_sha256'], 'mode': settings['mode'], 'human_review_required': True})
                db.execute("UPDATE business_budget_roots SET status='completed' WHERE id=? AND status='active'", (ident,))
        except Exception as exc:
            with self.store.transaction() as db:
                run = self.store.get('runs', ident)
                if run['status'] not in TERMINAL:
                    run['status'], run['exit_reason'] = 'failed', getattr(exc, 'code', 'DSH_RUNTIME_FAILED')
                    self.store.event(db, run, 'run.failed', {'error_code': run['exit_reason']})
                    db.execute("UPDATE business_budget_roots SET status='failed' WHERE id=? AND status='active'", (ident,))

    def recover(self):
        self.cleanup_status = cleanup_workspaces(Path(os.getenv('HARNESS_DSH_RUN_ROOT', ROOT / '.local/dsh-runs')))
        # No automatic resume/model replay after restart.
        for run in self.store.listing('runs'):
            if run['selected_engine'] != ENGINE or run['status'] in TERMINAL:
                continue
            with self.store.transaction() as db:
                run['status'], run['exit_reason'] = 'failed', 'DSH_SERVER_RESTARTED'
                self.store.event(db, run, 'run.failed', {'error_code': run['exit_reason']})
                db.execute("UPDATE business_budget_calls SET status='unknown' WHERE root_id=? AND status='sent'", (run['id'],))
                db.execute("UPDATE business_budget_roots SET status='stopped_on_restart' WHERE id=? AND status='active'", (run['id'],))
