"""Real-Provider probe: a few synthetic payment contracts through official DSH + doubao.

Explicitly opted in by the user (2026-10-06). Uses the existing Keychain
credential *reference*; the value is never printed or written. Temporary DB and
run directories only; scoring against labels happens after all runs.

    HARNESS_DSH_CREDENTIAL_REF=<ref> .venv/bin/python harness/dsh_real_payment_probe.py \
        --cases pay-01,pay-05,pay-09,pay-13,pay-17 --out harness/evidence/HA-0080/real_runs.json
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
EVAL = ROOT / 'harness/eval/dsh_payment'


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--cases', required=True)
    parser.add_argument('--out', required=True)
    parser.add_argument('--timeout', type=int, default=240)
    parser.add_argument('--context-window', type=int, default=None,
                        help='probe-only override to force context stubbing; production uses 64000')
    args = parser.parse_args()
    if not os.getenv('HARNESS_DSH_CREDENTIAL_REF'):
        raise SystemExit('HARNESS_DSH_CREDENTIAL_REF is required (a Keychain reference, not a key)')
    wanted = args.cases.split(',')
    cases = [c for c in json.loads((EVAL / 'cases.json').read_text())['cases'] if c['id'] in wanted]
    from fastapi.testclient import TestClient
    from backend.app import create_app
    if args.context_window:
        import functools
        import backend.dsh_runtime as runtime
        from backend.dsh_context import assemble
        runtime.assemble_context = functools.partial(assemble, context_window=args.context_window)
    rows = []
    with tempfile.TemporaryDirectory() as tmp:
        base = Path(tmp).resolve()
        os.environ.update({'HARNESS_DSH_LOCAL': 'enabled', 'HARNESS_DSH_REAL_ENABLED': '1',
                           'HARNESS_DSH_RUN_ROOT': str(base / 'owned')})
        with TestClient(create_app(base / 'real.db', run_worker=False), base_url='http://localhost') as client:
            rt = client.app.state.service.dsh
            for case in cases:
                body = {'objective': case['objective'], 'document': case['document'], 'mode': 'real_provider',
                        'public_data_confirmed': True, 'template': 'payment_terms',
                        'timeout_seconds': min(300, args.timeout), 'token_limit': 20_000_000}
                response = client.post('/api/local/dsh/runs', json=body, headers={'Idempotency-Key': 'real-' + case['id']})
                response.raise_for_status()
                ident = response.json()['initial_run']['id']
                started = time.monotonic()
                rt.execute(ident)
                detail = rt.detail(ident)
                events = rt.store.events(ident)
                record = None
                for artifact in detail['artifacts']:
                    if artifact['name'] == 'dsh-findings.json':
                        raw = rt.store.db.execute('SELECT body FROM artifacts WHERE id=?', (artifact['id'],)).fetchone()[0]
                        record = json.loads(raw)
                checks = [e['data'] for e in events if e['event_type'] == 'dsh.findings.checked']
                rows.append({'id': case['id'], 'family': case['family'], 'run_id': ident,
                             'status': detail['run']['status'], 'exit_reason': detail['run']['exit_reason'],
                             'seconds': round(time.monotonic() - started, 1),
                             'model_calls': detail['budget']['calls'], 'tokens': detail['budget']['spent'],
                             'reserved_after': detail['budget']['reserved'],
                             'tool_events': [e['data']['tool'] for e in events if e['event_type'] == 'dsh.tool.completed'],
                             'findings_checks': checks, 'record': record,
                             'context': [{k: e['data'][k] for k in ('estimate_before', 'estimate_after', 'budget',
                                                                    'stubbed_tool_results')}
                                         for e in events if e['event_type'] == 'dsh.context.assembled']})
                print(json.dumps({k: rows[-1][k] for k in ('id', 'status', 'exit_reason', 'model_calls', 'tokens', 'seconds')},
                                 ensure_ascii=False), flush=True)
    labels = {l['id']: l for l in json.loads((EVAL / 'labels.json').read_text())['labels']}
    for row in rows:  # scoring only after every run finished
        label, record = labels[row['id']], row['record'] or {}
        term = (record.get('findings') or {}).get('term', {})
        exception = (record.get('findings') or {}).get('exception', {})
        gold = label['exception_clause']
        row['score'] = {
            'term_value_matches_label': bool(term) and str(label['true_value']) in term.get('claim', '')
                                        and label['unit'].replace('个', '') in term.get('claim', ''),
            'exception_gold': gold,
            'exception_reported_as_finding': bool(gold) and any(q['clause_id'] == gold for q in exception.get('quotes', [])),
            'exception_reported_as_gap': bool(gold) and any(gold in g['clause_ids'] for g in record.get('platform_gaps', [])),
            'false_exception_finding': (not gold) and exception.get('status') == 'supported',
        }
    report = {'probe': 'dsh-real-payment@1', 'context_window_override': args.context_window, 'provider': 'doubao-seed-2.1-lite via Ark coding/v3',
              'note': 'synthetic public contracts; real model behaviour on 5 cases, not a statistical quality claim',
              'rows': rows, 'tokens_total': sum(r['tokens'] for r in rows),
              'model_calls_total': sum(r['model_calls'] for r in rows)}
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(report, ensure_ascii=False, indent=1) + '\n')


if __name__ == '__main__':
    main()
