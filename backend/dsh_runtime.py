"""DSH Product Run orchestration; platform owns policy, credentials, budget and publication."""
from __future__ import annotations
import asyncio
import copy
import json
import os
from pathlib import Path
import re
import subprocess
import threading
import time
import unicodedata
import httpx
from jsonschema import Draft202012Validator

from adapters.dsh import DshAdapter
from adapters.dsh_workspace import cleanup_workspaces
from .agent_runtime import KeyringCredentialResolver, reject_sensitive
from .adaptive_retrieval import build_parent_child_chunks
from .analysis import Problem, digest
from .business_budget import BusinessTokenLedger, budgeted_model_call
from .dsh_context import assemble as assemble_context
from .dsh_crossings import Crossings, initialize as initialize_crossings, retire as retire_crossings
from .dsh_plan import PLAN_VERSION, failed_step as plan_failed_step, failure_point as plan_failure_point, project as project_plan, summary as plan_summary
from .dsh_output_scan import SCAN_VERSION, scan as scan_output
from .dsh_findings import candidates as finding_candidates, render_text as render_findings, verify as verify_findings
from .dsh_provider import MODEL, BASE, TOOL_NAMES, FINDINGS_TOOL, provider_payload, send_real, send_probe, tool_names_for
from .service import ROOT, DENY, TERMINAL, validate
from .store import dumps, uid, now

ENGINE = 'engine_dsh_document'
SEARCH_PAGE = 3
MAX_MODEL_CALLS = 8
MAX_TOOL_CALLS = 32  # HA-0081: was 16; long contracts with real doubao exceeded it (model calls stay 8)
MAX_FINDINGS_REJECTIONS = 2
# HA-0099: a well-formed but non-existent block ID is a correctable model error, returned
# as an observation with a hint (jikesummary 工具六大契约: red/yellow errors with hints).
# Bounded; anything else (paths, malformed IDs, policy) still fails the Run.
MAX_SOFT_TOOL_ERRORS = 2
CLAUSE_ID = re.compile(r'clause-[1-9][0-9]{0,5}')
# Content digests of the files that define the model-facing contract and the validator.
CONTRACT_SHA256 = digest(b''.join((ROOT / f).read_bytes() for f in (
    'dsh-adapter/platform-plugin.mjs', 'dsh-adapter/controlled.patch.yml')))
VALIDATOR_SHA256 = digest((ROOT / 'backend/dsh_findings.py').read_bytes())


def search_key(text):
    """HA-0110: literal search tolerant of width/case/whitespace (NFKC, casefold, no spaces)."""
    return re.sub(r'\s+', '', unicodedata.normalize('NFKC', text)).casefold()
# Progress is judged per model turn (HA-0081, after real doubao issued 5 parallel
# searches in one turn): a turn makes progress if any of its actions brought new
# evidence. Stop before the next model request when
MAX_REPEATED_NO_PROGRESS = 2  # two consecutive turns consisting only of repeated actions, or
MAX_NO_PROGRESS = 3           # three consecutive turns without any new evidence.
SCHEMA = json.loads((ROOT / 'specs/v1/dsh-runtime.schema.json').read_text())


def validate_dsh(kind, value):
    validator = Draft202012Validator({'$ref': '#/$defs/' + kind, '$defs': SCHEMA['$defs']})
    if list(validator.iter_errors(value)):
        raise Problem('DSH_VALIDATION_ERROR', 'DSH 数据不满足契约。', 422)


class DshRuntime:
    def __init__(self, service):
        self.service, self.store = service, service.store
        self.ledger = BusinessTokenLedger(self.store)
        initialize_crossings(self.store)
        self.adapter = DshAdapter()
        self.send_probe = send_probe
        self.send_real = send_real
        self.credentials = KeyringCredentialResolver()
        self.release = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip()
        # DSH-CLEANUP-01: bounded delayed retries for registered workspaces left pending at startup.
        self.cleanup_retry_seconds = float(os.getenv('HARNESS_DSH_CLEANUP_RETRY_SECONDS', '10'))
        self.cleanup_retry_limit = 6
        # A full structured submission can take >45 s on doubao-seed-2.1-lite (HA-0082 real run).
        self.provider_timeout_seconds = 120
        self._cleanup_timer = None
        self._cleanup_stopped = threading.Event()
        self._cleanup_root = None

    def status(self):
        available = (ROOT / 'dsh-adapter/node_modules/@deepseek-ai/dsh/lib/bin.js').is_file()
        return {'engine': ENGINE, 'runtime': 'deepseek-harness@0.2.1-alpha.1', 'release': self.release,
                'installed': available, 'integration_probe': available,
                'real_provider_enabled': os.getenv('HARNESS_DSH_REAL_ENABLED') == '1',
                'credential_ref_configured': bool(os.getenv('HARNESS_DSH_CREDENTIAL_REF')),
                'workspace_recovery': getattr(self, 'cleanup_status', None),
                'model': MODEL, 'base_url': BASE, 'tools': sorted(TOOL_NAMES),
                'shell_enabled': False, 'network_tools_enabled': False,
                'max_model_calls': MAX_MODEL_CALLS, 'max_tool_calls': MAX_TOOL_CALLS, 'max_token_limit': 20_000_000,
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
                    'mode': body['mode'], 'template': body.get('template', 'free'), 'token_limit': body.get('token_limit', 20000000 if body['mode'] == 'real_provider' else 200000),
                    'billing_mode': 'coding_plan_no_balance_fallback' if body['mode'] == 'real_provider' else 'synthetic',
                    'credential_ref': os.getenv('HARNESS_DSH_CREDENTIAL_REF') if body['mode'] == 'real_provider' else None}},
                'engine_policy': {'mode': 'explicit', 'engine_id': ENGINE,
                                  'required_capabilities': ['actions.tool_call', 'artifacts.files', 'control.cancel']},
                'model_policy': {'text_and_code': MODEL if body['mode'] == 'real_provider' else 'synthetic:dsh-integration-probe',
                                 'vision': None, 'allow_fallback': False},
                'requested_permissions': {'profile': 'analysis_read_only', 'profile_version': 1,
                                         'allow_tools': sorted(tool_names_for(body.get('template', 'free'))), 'deny_capabilities': list(DENY)},
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
            'allowed_tools': sorted(task['requested_permissions']['allow_tools']), 'denied_capabilities': list(DENY),
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

    def _plan_history(self, ident):
        """Replay every event in bounded pages; caller holds the Store lock.

        The public events API is one page, not a complete projection source.
        Advance by the actual sequence so sparse histories and short pages work.
        """
        after = 0
        while True:
            page = self.store.events(ident, after)
            if not page:
                return
            yield from page
            after = page[-1]['sequence']

    def detail(self, ident):
        with self.store.lock:
            run = self.store.get('runs', ident)
            if run['selected_engine'] != ENGINE:
                raise Problem('NOT_FOUND', 'DSH Run 不存在。', 404)
            task = self.store.get('tasks', run['task_id'])
            row = self.store.db.execute('SELECT 1 FROM business_budget_roots WHERE id=?', (ident,)).fetchone()
            plan = None
            for item in self._plan_history(ident):
                if item['event_type'] == 'dsh.plan.created':
                    plan = copy.deepcopy(item['data'])
                elif item['event_type'] == 'dsh.plan.step' and plan:
                    updates = {st['step_id']: st for st in item['data']['steps']}
                    for st in plan['steps']:
                        st.update(updates.get(st['step_id'], {}))
                elif item['event_type'] == 'run.succeeded' and plan and item['data'].get('plan_status'):
                    for st in plan['steps']:
                        st['status'] = item['data']['plan_status'].get(st['step_id'], st['status'])
            return {'run': run, 'task': task, 'artifacts': self.store.artifact_list(ident), 'plan': plan,
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
        plan_box = {'plan': None}
        crossings = None
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
            search_index = {key: search_key(text) for key, text in clauses.items()}
            seen_clauses = set()
            template = settings.get('template', 'free')
            allowed = set(task['requested_permissions']['allow_tools'])
            progress = {'fingerprints': set(), 'no_progress': 0, 'repeats': 0, 'notices': 0, 'read': set(), 'soft_errors': 0,
                        'turn': None}
            review = {'rejections': 0, 'coverage_warned': False, 'accepted': None, 'submissions': 0}
            context = {'stubbed': set(), 'last': None}
            all_candidates = finding_candidates(clauses) if template == 'payment_terms' else {'payment': [], 'exception': []}
            exception_candidates = all_candidates['exception']
            review.setdefault('history', [])
            deadline = time.monotonic() + task['limits']['timeout_seconds']
            def check():
                self.service.check(ident)
                if time.monotonic() >= deadline:
                    raise Problem('TIMEOUT', 'DSH 已到截止时间。', 409)
            def event(kind, value, *extra):
                # One transaction per platform action: an audit/tool event and the plan
                # projection it causes commit together or not at all (HA-0082 review M1).
                with self.store.transaction() as db:
                    check()
                    run_doc = self.store.get('runs', ident)
                    for k, v in ((kind, value), *extra):
                        self.store.event(db, run_doc, k, v)
            def plan_update(published=False):
                """Compute the next projection without committing it; returns (plan, events)."""
                if template != 'payment_terms':
                    return None, []
                previous = plan_box['plan']
                plan = project_plan(all_candidates, seen_clauses,
                    {'submissions': review['submissions'], 'accepted': review['accepted'] is not None,
                     'last_codes': review.get('last_codes')}, published)
                keys = ('step_id', 'status', 'evidence_ids', 'missing_ids', 'error_codes')
                if previous is None:
                    return plan, [('dsh.plan.created', plan)]
                if [[a[k] for k in keys] for a in previous['steps']] != [[b[k] for k in keys] for b in plan['steps']]:
                    return plan, [('dsh.plan.step', {'steps': [{k: st[k] for k in keys} for st in plan['steps']]})]
                return plan, []
            def commit(kind, value):
                """Write an action event plus its plan change atomically; adopt the plan only after commit."""
                plan, extra = plan_update()
                event(kind, value, *extra)
                if plan is not None:
                    plan_box['plan'] = plan
            def emit(value):
                validate_dsh('observation', value)
                event('dsh.observation', value)
            def close_turn():
                turn, progress['turn'] = progress['turn'], None
                if turn is None:
                    return
                if turn['new']:
                    progress['no_progress'], progress['repeats'] = 0, 0
                else:
                    progress['no_progress'] += 1
                    progress['repeats'] = progress['repeats'] + 1 if turn['all_repeated'] else 0
                if progress['repeats'] >= MAX_REPEATED_NO_PROGRESS or progress['no_progress'] >= MAX_NO_PROGRESS:
                    event('dsh.progress.stopped', {'no_progress_turns': progress['no_progress'],
                                                   'repeat_turns': progress['repeats']})
                    raise Problem('DSH_NO_PROGRESS', '连续多轮没有带来新证据，提前停止。', 409)
            def model_call(request):
                check()
                close_turn()  # judged before spending another model request
                if counts['model_calls'] >= 8:
                    raise Problem('DSH_MODEL_CALL_LIMIT', '达到 8 次模型调用上限。', 409)
                payload = provider_payload(request, allowed)
                state = {'template': template,
                         'read': sorted(seen_clauses, key=lambda k: int(k.split('-')[1])),
                         'unread_exception_candidates': [k for k in exception_candidates if k not in seen_clauses],
                         'submission': ({'number': review['submissions'], 'accepted': review['accepted'] is not None,
                                         'error_codes': list(review.get('last_codes') or [])}
                                        if review['submissions'] else None),
                         'plan': plan_summary(plan_box['plan']) if plan_box['plan'] else None}
                payload, assembly = assemble_context(payload, state)
                context['stubbed'] = set(assembly['invisible_clause_ids'])  # only blocks with no full copy sent
                event('dsh.context.assembled', dict(assembly, call_number=counts['model_calls'] + 1))
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
                            send=send, timeout_seconds=min(self.provider_timeout_seconds, max(.1, deadline-time.monotonic())), cancel_event=cancel)
                    except asyncio.CancelledError:
                        check()
                        raise Problem('DSH_CANCELLED', 'DSH 已取消。', 409) from None
                    except (TimeoutError, httpx.TimeoutException):
                        check()  # the Run deadline wins if it is the cause
                        # Sent but unanswered: usage is unknown and stays frozen; no automatic retry.
                        raise Problem('DSH_PROVIDER_TIMEOUT', 'Provider 响应超时；用量未知，不自动重试。', 504) from None
                    finally:
                        watcher.cancel()
                        await asyncio.gather(watcher, return_exceptions=True)
                started = time.monotonic()
                result = asyncio.run(controlled_call())
                latency_ms = int((time.monotonic() - started) * 1000)  # numbers only (HA-0097)
                check()
                if any(call['name'] not in allowed for call in result['tool_calls']):
                    # Defense in depth: a tool this Run does not offer is a policy error, not a retry loop.
                    raise Problem('DSH_TOOL_POLICY', '模型请求了本 Run 未提供的工具。', 403)
                event('dsh.model.completed', {'call_number': counts['model_calls'],
                    'mode': settings['mode'], 'usage': result['usage'], 'latency_ms': latency_ms})
                return result
            def tool_call(body):
                tool_started = time.monotonic()
                check()
                if not isinstance(body, dict) or set(body) != {'name', 'arguments'} or body['name'] not in allowed:
                    raise Problem('DSH_TOOL_POLICY', '工具未准入。', 403)
                if counts['tool_calls'] >= MAX_TOOL_CALLS:
                    raise Problem('DSH_TOOL_LIMIT', '达到工具上限。', 409)
                if body['name'] == FINDINGS_TOOL:
                    return submit_findings(body['arguments'])
                args = body['arguments']
                if body['name'] == 'read_clause':
                    if (not isinstance(args, dict) or set(args) != {'clause_id'} or
                            not isinstance(args['clause_id'], str) or not 1 <= len(args['clause_id']) <= 200):
                        raise Problem('DSH_TOOL_INPUT', '工具参数无效。', 422)
                    soft_error = None
                    if args['clause_id'] not in clauses:
                        if not CLAUSE_ID.fullmatch(args['clause_id']) or progress['soft_errors'] >= MAX_SOFT_TOOL_ERRORS:
                            raise Problem('DSH_CLAUSE_NOT_FOUND', '条款不存在。', 404)
                        progress['soft_errors'] += 1
                        soft_error = 'CLAUSE_NOT_FOUND'
                    selected, page = ([] if soft_error else [args['clause_id']]), None
                else:
                    if (not isinstance(args, dict) or 'query' not in args or set(args) - {'query', 'offset'} or
                            not isinstance(args['query'], str) or not 1 <= len(args['query']) <= 200 or
                            type(args.get('offset', 0)) is not int or not 0 <= args.get('offset', 0) <= 1000):
                        raise Problem('DSH_TOOL_INPUT', '工具参数无效。', 422)
                    soft_error = None
                    query, offset = search_key(args['query']), args.get('offset', 0)
                    if not query:  # whitespace-only would otherwise match every block
                        raise Problem('DSH_TOOL_INPUT', '工具参数无效。', 422)
                    matches = [key for key, text in search_index.items() if query in text]
                    selected = matches[offset:offset + SEARCH_PAGE]
                    more = offset + SEARCH_PAGE < len(matches)
                    page = {'total': len(matches), 'offset': offset,
                            'next_offset': offset + SEARCH_PAGE if more else None, 'truncated': more}
                counts['tool_calls'] += 1
                # Progress is judged by the platform: same normalized action or no
                # clause the model has not already received is not new evidence.
                fingerprint = digest(dumps({'tool': body['name'], 'args': args, 'resource': task['context']['resource_ids'][0]}).encode())
                # New evidence: a search returning a block the model never received, or the
                # first explicit read of a block (reading a search hit in full is legitimate).
                if body['name'] == 'read_clause':
                    # Re-reading a block whose text the assembler stubbed out is legitimate.
                    new = [key for key in selected if key not in progress['read'] or key in context['stubbed']]
                    progress['read'].update(selected)
                    context['stubbed'] -= set(selected)
                else:
                    new = [key for key in selected if key not in seen_clauses]
                repeated = fingerprint in progress['fingerprints']
                progress['fingerprints'].add(fingerprint)
                turn = progress['turn'] = progress['turn'] or {'actions': 0, 'new': 0, 'all_repeated': True}
                turn['actions'] += 1
                turn['new'] += len(new)
                turn['all_repeated'] = turn['all_repeated'] and repeated
                seen_clauses.update(selected)
                commit('dsh.tool.completed', {'tool': body['name'], 'call_number': counts['tool_calls'],
                    'clause_ids': selected, 'arguments_sha256': digest(dumps(args).encode()),
                    'new_evidence': len(new), 'repeated_action': repeated,
                    'no_progress_turns': progress['no_progress'], 'repeat_turns': progress['repeats'],
                    'latency_ms': int((time.monotonic() - tool_started) * 1000),
                    **({'error_code': soft_error} if soft_error else {}),
                    **({'total_matches': page['total'], 'truncated': page['truncated']} if page else {})})
                value = {'matches': [{'clause_id': key, 'text': clauses[key]} for key in selected]}
                if page:
                    value.update(page)
                if soft_error:
                    return {'text': dumps(dict(value, error=soft_error,
                        hint=f'证据块编号范围是 clause-1 到 clause-{len(clauses)}；请先用 search_document 定位再读取。'
                             f'该类错误本 Run 最多容忍 {MAX_SOFT_TOOL_ERRORS} 次。'))}
                # Warn on the action itself when it adds nothing and the run is already one
                # turn away from the stop rule.
                warn = not new and (repeated or progress['no_progress'] >= MAX_NO_PROGRESS - 1)
                if warn:
                    progress['notices'] += 1
                    value['notice'] = ('NO_NEW_EVIDENCE：本次没有带来新的证据块。换一个不同的查询或读取未读证据块；'
                                       '若已无可读证据，请据已有证据作答并说明缺口。继续无进展将停止。')
                return {'text': dumps(value) if page or warn else dumps(value['matches'])}
            def submit_findings(args):
                counts['tool_calls'] += 1
                review['submissions'] += 1
                number = review['submissions']
                # Policy: the *last* submission must pass. A rejected or gap-warned
                # replacement withdraws any earlier acceptance.
                review['accepted'] = None
                checked = verify_findings(args, clauses, seen_clauses)
                content_sha = digest(dumps(args).encode())
                for item in review['history']:  # a new submission supersedes every earlier one
                    item['superseded_by'] = item.get('superseded_by') or number
                if checked['errors']:
                    review['rejections'] += 1
                    codes = sorted({e['code'] for e in checked['errors']})
                    review['last_codes'] = codes
                    review['history'].append({'number': number, 'accepted': False, 'error_codes': codes,
                                              'content_sha256': content_sha, 'superseded_by': None})
                    commit('dsh.findings.checked', {'accepted': False, 'error_codes': codes, 'submission_number': number,
                        'content_sha256': content_sha, 'rejections': review['rejections']})
                    if review['rejections'] > MAX_FINDINGS_REJECTIONS:
                        raise Problem('DSH_FINDINGS_INVALID', '结构化结果多次未通过平台校验。', 409)
                    return {'text': dumps({'accepted': False, 'submission_number': number, 'errors': checked['errors'],
                        'hint': '引文必须逐字摘自本轮读过的证据块；结论中的数值、单位、甲乙方须出现在引文中；缺证据用 unknown。'})}
                gap = next((g for g in checked['platform_gaps'] if g['code'] == 'EXCEPTION_CANDIDATES_UNREAD'), None)
                if gap and not review['coverage_warned']:
                    review['coverage_warned'] = True
                    review['last_codes'] = ['COVERAGE_GAP']
                    review['history'].append({'number': number, 'accepted': False, 'error_codes': ['COVERAGE_GAP'],
                                              'content_sha256': content_sha, 'superseded_by': None})
                    commit('dsh.findings.checked', {'accepted': False, 'error_codes': ['COVERAGE_GAP'],
                        'submission_number': number, 'content_sha256': content_sha, 'rejections': review['rejections']})
                    return {'text': dumps({'accepted': False, 'submission_number': number, 'coverage_gap': gap,
                        'hint': '平台发现未读的付款例外候选证据块。请读取后重新提交；确实无法读取时可再次提交，将记为部分结果。'})}
                review['accepted'] = dict(checked, submission_number=number, read_at_submission=sorted(seen_clauses))
                review['last_codes'] = []
                review['history'].append({'number': number, 'accepted': True, 'error_codes': [],
                                          'content_sha256': content_sha, 'superseded_by': None})
                commit('dsh.findings.checked', {'accepted': True, 'submission_number': number, 'content_sha256': content_sha,
                    'business_status': checked['business_status'],
                    'platform_gap_count': len(checked['platform_gaps']), 'model_gap_count': len(checked['model_gaps'])})
                return {'text': dumps({'accepted': True, 'submission_number': number, 'business_status': checked['business_status'],
                    'platform_gaps': checked['platform_gaps']})}
            prompt = (f'平台文档已登记为 {len(clauses)} 个证据块，ID 范围 clause-1 到 clause-{len(clauses)}。'
                      'ID 是平台证据块编号，不等于合同原文条号。search_document 是字面子串检索（忽略空白、大小写和全半角差异），不支持正则。\n'
                      + ('这是付款条件核对：请检索并读取付款期限、触发条件、例外和冲突相关证据块，'
                         '调用 submit_findings 提交四个槽位（缺证据用 unknown，不要猜）；平台只发布最后一次通过校验的结构化结果，不发布你的自由文本答复。\n'
                         if template == 'payment_terms' else '')
                      + task['objective'])
            # HA-0113: what this Run was decided with (digests only; the objective is user text).
            versions = {'release': self.release, 'prompt_sha256': digest(prompt.encode()),
                        'tools': sorted(allowed), 'contract_sha256': CONTRACT_SHA256,
                        'validator_sha256': VALIDATOR_SHA256, 'plan_version': PLAN_VERSION}
            event('dsh.run.versions', versions)
            plan, created = plan_update()  # dsh.plan.created is persisted before the first model request
            if created:
                event(*created[0])
                plan_box['plan'] = plan
            crossings = Crossings(self.store, ident, check)
            result = self.adapter.run(prompt,
                Path(os.getenv('HARNESS_DSH_RUN_ROOT', ROOT / '.local/dsh-runs')), MODEL,
                lambda body: crossings.invoke('model', body, model_call),
                lambda body: crossings.invoke('tool', body, tool_call), emit, check,
                **({'tools': sorted(allowed)} if allowed != TOOL_NAMES else {}))
            validate_dsh('result', result)
            cited = set(re.findall(r'clause-[0-9]+', result['text']))
            if not counts['model_calls'] or not seen_clauses:
                raise Problem('DSH_EVIDENCE_NOT_READ', '没有读取文档证据，拒绝发布。', 409)
            if template == 'payment_terms':
                if review['accepted'] is None:
                    raise Problem('DSH_FINDINGS_MISSING', '付款核对的最后一次提交没有通过平台校验，拒绝发布。', 409)
            elif not cited or not cited <= seen_clauses:
                raise Problem('DSH_EVIDENCE_CITATION_INVALID', '引用必须指向本轮实际读取的证据块。', 409)
            with self.store.transaction() as db:
                check()
                retire_crossings(self.store, db, ident, crossings.generation)
                # Retirement emits events and advances sequence: read the updated Run.
                current = self.store.get('runs', ident)
                business = {}
                if template == 'payment_terms':
                    accepted = review['accepted']
                    record = {'schema_version': 'dsh-payment-findings@1', 'template': template,
                              'submission_number': accepted['submission_number'],
                              'business_status': accepted['business_status'], 'findings': accepted['findings'],
                              'model_gaps': accepted['model_gaps'], 'platform_gaps': accepted['platform_gaps'],
                              'candidates': accepted['candidates'], 'read_clause_ids': accepted['read_at_submission'],
                              'verification': 'quotes_literal_values_units_parties_checked_semantics_not_verified',
                              'submissions': [dict(item) for item in review['history']],
                              'human_review_required': True}
                    validate_dsh('findings', record)
                    # The analysis text is rendered from the verified record; the model's
                    # free-form final answer is not published in this template.
                    artifact = self.service.pi_contract_review._publish(
                        db, current, 'dsh-analysis.txt', render_findings(record), 'text/plain')
                    findings_artifact = self.service.pi_contract_review._publish(
                        db, current, 'dsh-findings.json', dumps(record), 'application/json')
                    final_plan = project_plan(all_candidates, seen_clauses,
                        {'submissions': review['submissions'], 'accepted': True, 'last_codes': []}, published=True)
                    business = {'business_status': accepted['business_status'],
                                'submission_number': accepted['submission_number'],
                                'plan_status': {st['step_id']: st['status'] for st in final_plan['steps']},
                                'findings_artifact_id': findings_artifact['id'], 'model_final_text_published': False}
                else:
                    artifact = self.service.pi_contract_review._publish(db, current, 'dsh-analysis.txt', result['text'], 'text/plain')
                    # Shadow mode: the model's free text is published unchanged; only counts are recorded.
                    counts_by_category = scan_output(result['text'])
                    self.store.event(db, current, 'dsh.output.scanned', {
                        'scan_version': SCAN_VERSION, 'mode': 'shadow', 'categories': counts_by_category,
                        'flagged': any(counts_by_category.values())})
                    business = {'output_scan_flagged': any(counts_by_category.values())}
                current['status'], current['exit_reason'] = 'succeeded', 'COMPLETED'
                self.store.event(db, current, 'run.succeeded', {'artifact_id': artifact['id'], **counts,
                    'session_sha256': result['session_sha256'], 'mode': settings['mode'],
                    'template': template, **business, 'human_review_required': True,
                    # HA-0113: kept out of dsh-findings.json so older findings readers still validate it.
                    'versions': {k: versions[k] for k in ('release', 'validator_sha256', 'plan_version')}})
                db.execute("UPDATE business_budget_roots SET status='completed' WHERE id=? AND status='active'", (ident,))
        except Exception as exc:
            with self.store.transaction() as db:
                run = self.store.get('runs', ident)
                if run['status'] not in TERMINAL:
                    if crossings is not None:
                        retire_crossings(self.store, db, ident, crossings.generation)
                        run = self.store.get('runs', ident)
                    run['status'], run['exit_reason'] = 'failed', getattr(exc, 'code', 'DSH_RUNTIME_FAILED')
                    failure = {'error_code': run['exit_reason']}
                    if plan_box['plan']:
                        # failed_step = earliest unfinished step (kept for compatibility);
                        # failure_point = where the failure is attributed (HA-0095).
                        failure['failed_step'] = plan_failed_step(plan_box['plan'])
                        failure['failure_point'] = plan_failure_point(plan_box['plan'], run['exit_reason'])
                    self.store.event(db, run, 'run.failed', failure)
                    db.execute("UPDATE business_budget_roots SET status='failed' WHERE id=? AND status='active'", (ident,))

        finally:
            if crossings is not None:
                with self.store.transaction() as db:
                    # Cancellation must not wait on the crossing lock/Provider. Late
                    # cleanup is allowed, but a failed terminal transaction must not
                    # be followed by an independent retirement commit on a live Run.
                    if self.store.get('runs', ident)['status'] in TERMINAL:
                        retire_crossings(self.store, db, ident, crossings.generation)

    def _run_root(self):
        # Fixed at recovery time so a later env change cannot widen a retry's scope.
        return self._cleanup_root or Path(os.getenv('HARNESS_DSH_RUN_ROOT', ROOT / '.local/dsh-runs'))

    def stop(self):
        self._cleanup_stopped.set()
        if self._cleanup_timer is not None:
            self._cleanup_timer.cancel()

    def _retry_cleanup(self, attempt):
        if self._cleanup_stopped.is_set():
            return
        # Same ownership rules as startup: registered entries only, lease released and
        # process group gone; never kills a recovered PID, never widens the scope.
        result = cleanup_workspaces(self._run_root(), wait_seconds=0)
        status = dict(self.cleanup_status or {})
        status['cleaned'] = status.get('cleaned', 0) + result['cleaned']
        status['retained'] = result['retained']  # retained entries stay registered; report current count
        status['pending'] = result['pending']
        status['retries'] = attempt
        self.cleanup_status = status
        if result['pending'] and attempt < self.cleanup_retry_limit:
            self._schedule_cleanup(attempt + 1)

    def _schedule_cleanup(self, attempt):
        if self._cleanup_stopped.is_set():
            return
        self._cleanup_timer = threading.Timer(self.cleanup_retry_seconds, self._retry_cleanup, args=(attempt,))
        self._cleanup_timer.daemon = True
        self._cleanup_timer.start()

    def recover(self):
        self._cleanup_root = Path(os.getenv('HARNESS_DSH_RUN_ROOT', ROOT / '.local/dsh-runs'))
        self.cleanup_status = dict(cleanup_workspaces(self._run_root()), retries=0)
        if self.cleanup_status['pending']:
            self._schedule_cleanup(1)
        # No automatic resume/model replay after restart.
        for run in self.store.listing('runs'):
            if run['selected_engine'] != ENGINE:
                continue
            with self.store.transaction() as db:
                retire_crossings(self.store, db, run['id'])
                if run['status'] in TERMINAL:
                    continue
                run = self.store.get('runs', run['id'])
                run['status'], run['exit_reason'] = 'failed', 'DSH_SERVER_RESTARTED'
                self.store.event(db, run, 'run.failed', {'error_code': run['exit_reason']})
                db.execute("UPDATE business_budget_calls SET status='unknown' WHERE root_id=? AND status='sent'", (run['id'],))
                db.execute("UPDATE business_budget_roots SET status='stopped_on_restart' WHERE id=? AND status='active'", (run['id'],))
