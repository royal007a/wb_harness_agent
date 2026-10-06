"""HA-0079 fixed evaluation: platform control logic on synthetic payment documents.

Runs the official DSH SDK subprocess with a scripted synthetic Provider. The
script and the runtime only see ``cases.json``; ``labels.json`` is read after
all runs finish, for scoring. This measures what the *platform* catches, not
model quality: the scripted model is deliberately naive and label-blind.

    .venv/bin/python harness/dsh_payment_eval.py --out harness/evidence/HA-0079/eval.json
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
EVAL = ROOT / 'harness/eval/dsh_payment'


def scripted_provider(case):
    """Label-blind naive policy: first search page only; reads more only when the platform asks."""
    from backend.dsh_provider import parse_response
    claimed, unit = case['script']['claimed_value'], case['script']['unit']

    def reply(text='', calls=()):
        message = {'content': text}
        if calls:
            message['tool_calls'] = [{'id': f'c{i}', 'type': 'function', 'function': {
                'name': n, 'arguments': json.dumps(a, ensure_ascii=False)}} for i, (n, a) in enumerate(calls)]
        return parse_response({'choices': [{'finish_reason': 'tool_calls' if calls else 'stop', 'message': message}],
                               'usage': {'prompt_tokens': 10, 'completion_tokens': 10, 'total_tokens': 20}})

    state = {'clauses': {}, 'exception': None}

    def findings():
        # first read sentence that states a payment period (label-blind)
        term_id, sentence = next((k, m.group(0)) for k, t in state['clauses'].items()
                                 for m in [re.search(r'[^。\n]*验收合格[^。]*?[0-9]+(?:个工作日|天)内[^。]*', t)] if m)
        unknown = {'status': 'unknown', 'claim': '', 'quotes': []}
        exception = unknown
        if state['exception']:
            ident = state['exception']
            text = state['clauses'][ident].split('\n')[-1].rstrip('。')
            exception = {'status': 'supported', 'claim': text, 'quotes': [{'clause_id': ident, 'text': text}]}
        return {'term': {'status': 'supported', 'claim': f'验收合格后{claimed}{unit}内付款',  # value may be misstated by design
                         'quotes': [{'clause_id': term_id, 'text': sentence}]},
                'trigger': {'status': 'supported', 'claim': '验收合格',
                            'quotes': [{'clause_id': term_id, 'text': '验收合格'}]},
                'exception': exception, 'conflict': unknown}

    async def provider(payload, limit):
        results = [json.loads(m['content']) for m in payload['messages'] if m['role'] == 'tool']
        if not results:
            return reply(calls=[('search_document', {'query': '付款'})])
        last = results[-1]
        for item in (last.get('matches', []) if isinstance(last, dict) else last):
            state['clauses'][item['clause_id']] = item['text']
        if isinstance(last, dict) and last.get('accepted') is True:
            return reply('已提交付款核对结果，见 clause-1。')
        if isinstance(last, dict) and 'coverage_gap' in last:
            ids = last['coverage_gap']['clause_ids']
            state['exception'] = ids[0]
            return reply(calls=[('read_clause', {'clause_id': ident}) for ident in ids[:2]])
        return reply(calls=[('submit_findings', findings())])
    return provider


def run_case(case, workdir):
    from fastapi.testclient import TestClient
    from backend.app import create_app
    os.environ['HARNESS_DSH_LOCAL'] = 'enabled'
    os.environ['HARNESS_DSH_RUN_ROOT'] = str(workdir / 'owned')
    os.environ.pop('HARNESS_DSH_REAL_ENABLED', None)
    with TestClient(create_app(workdir / 'eval.db', run_worker=False), base_url='http://localhost') as client:
        body = {'objective': case['objective'], 'document': case['document'], 'mode': 'integration_probe',
                'public_data_confirmed': True, 'template': 'payment_terms'}
        response = client.post('/api/local/dsh/runs', json=body, headers={'Idempotency-Key': case['id']})
        response.raise_for_status()
        ident = response.json()['initial_run']['id']
        rt = client.app.state.service.dsh
        rt.send_probe = scripted_provider(case)
        rt.execute(ident)
        detail = rt.detail(ident)
        events = rt.store.events(ident)
        record = None
        for artifact in detail['artifacts']:
            if artifact['name'] == 'dsh-findings.json':
                body = rt.store.db.execute('SELECT body FROM artifacts WHERE id=?', (artifact['id'],)).fetchone()[0]
                record = json.loads(body)
        return {'id': case['id'], 'status': detail['run']['status'], 'exit_reason': detail['run']['exit_reason'],
                'model_calls': detail['budget']['calls'], 'tokens': detail['budget']['spent'],
                'coverage_warned': any(e['event_type'] == 'dsh.findings.checked' and
                                       e['data'].get('error_codes') == ['COVERAGE_GAP'] for e in events),
                'record': record}


def score(results, labels):
    by_id = {label['id']: label for label in labels}
    rows, totals = [], {}
    def add(key, ok):
        hit, n = totals.get(key, (0, 0))
        totals[key] = (hit + bool(ok), n + 1)
    for result in results:
        label = by_id[result['id']]
        record = result['record'] or {}
        published_value = None
        if record:
            published_value = record['findings']['term']['claim']
        if label['value_misstated_by_script']:
            add('misstated_value_not_published', result['status'] != 'succeeded'
                and result['exit_reason'] == 'DSH_FINDINGS_INVALID')
        else:
            add('correct_value_published', result['status'] == 'succeeded'
                and str(label['true_value']) in (published_value or ''))
            gold = label['exception_clause']
            candidates = (record.get('candidates') or {}).get('exception', [])
            exception = (record.get('findings') or {}).get('exception', {})
            as_finding = exception.get('status') == 'supported' and \
                any(q['clause_id'] == gold for q in exception.get('quotes', []))
            as_gap = any(gold in g['clause_ids'] for g in record.get('platform_gaps', []))
            surfaced = gold and (as_finding or as_gap)
            if gold and not label['exception_implicit']:
                add('lexical_exception_surfaced', surfaced)
            if gold and label['exception_implicit']:
                add('implicit_exception_detected_by_platform_lexicon', gold in candidates)
            if not gold:
                add('no_false_exception_candidate', not candidates)
        rows.append({'id': result['id'], 'family': label['family'], 'status': result['status'],
                     'exit_reason': result['exit_reason'], 'model_calls': result['model_calls'],
                     'coverage_warned': result['coverage_warned'],
                     'business_status': record.get('business_status')})
    return rows, {key: {'hit': hit, 'n': n} for key, (hit, n) in sorted(totals.items())}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--out', required=True)
    args = parser.parse_args()
    cases = json.loads((EVAL / 'cases.json').read_text())['cases']
    results = []
    with tempfile.TemporaryDirectory() as tmp:
        for case in cases:
            path = Path(tmp).resolve() / case["id"]
            path.mkdir()
            results.append(run_case(case, path))
    labels = json.loads((EVAL / 'labels.json').read_text())['labels']  # only after all runs
    rows, metrics = score(results, labels)
    report = {'eval': 'dsh-payment-control@1', 'cases': len(cases), 'provider': 'synthetic scripted (label-blind)',
              'measures': 'platform control logic only; not model quality',
              'metrics': metrics, 'rows': rows,
              'model_calls_total': sum(r['model_calls'] for r in rows)}
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(report, ensure_ascii=False, indent=1) + '\n')
    print(json.dumps(metrics, ensure_ascii=False))


if __name__ == '__main__':
    main()
