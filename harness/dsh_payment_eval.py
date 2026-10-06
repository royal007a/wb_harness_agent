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


def _case_ids(items):
    ids = [item.get('id') for item in items]
    if not ids or any(not isinstance(ident, str) or not ident for ident in ids) or len(set(ids)) != len(ids):
        raise ValueError('case IDs must be non-empty and unique')
    return set(ids)


def _scorable_record(record):
    """Minimum shape used by this fixed script's metrics, not a production validator."""
    if not isinstance(record, dict):
        return False
    findings, candidates = record.get('findings'), record.get('candidates')
    if not isinstance(findings, dict) or not isinstance(candidates, dict):
        return False
    term, exception = findings.get('term'), findings.get('exception')
    return (isinstance(term, dict) and term.get('status') == 'supported'
            and isinstance(term.get('claim'), str) and isinstance(exception, dict)
            and isinstance(exception.get('quotes'), list)
            and isinstance(candidates.get('exception'), list)
            and all(isinstance(x, str) for x in candidates['exception']))


def _script_period_matches(claim, label):
    # Independent oracle: don't reuse the runtime's numerical/semantic validators.
    # Unsupported natural-language expressions score unconfirmed, not semantically wrong.
    match = re.fullmatch(r'验收合格后([1-9][0-9]*)(天|个工作日)内付款', claim)
    return (match is not None and type(label['true_value']) is int
            and int(match[1]) == label['true_value'] and match[2] == label['unit'])


def score(results, labels):
    if _case_ids(results) != _case_ids(labels):
        raise ValueError('result and label case IDs must match exactly')
    by_id = {label['id']: label for label in labels}
    rows, totals = [], {}
    def add(key, ok):
        hit, n = totals.get(key, (0, 0))
        totals[key] = (hit + bool(ok), n + 1)
    for result in results:
        label = by_id[result['id']]
        valid = result['status'] == 'succeeded' and _scorable_record(result['record'])
        record = result['record'] if valid else {}
        published_value = None
        if record:
            published_value = record['findings']['term']['claim']
        if label['value_misstated_by_script']:
            add('misstated_value_not_published', result['status'] == 'failed'
                and result['exit_reason'] == 'DSH_FINDINGS_INVALID' and result['record'] is None)
        else:
            add('correct_value_published', valid and _script_period_matches(published_value, label))
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
                add('no_false_exception_candidate', valid and not candidates)
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
    report = {'eval': 'dsh-payment-control@2', 'scoring_version': 'fixed-script-value-unit@2',
              'cases': len(cases), 'provider': 'synthetic scripted (label-blind)',
              'measures': 'platform control logic only; not model quality',
              'metrics': metrics, 'rows': rows,
              'model_calls_total': sum(r['model_calls'] for r in rows)}
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(report, ensure_ascii=False, indent=1) + '\n')
    print(json.dumps(metrics, ensure_ascii=False))


if __name__ == '__main__':
    main()
