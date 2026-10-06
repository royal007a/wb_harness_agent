"""HA-0082: platform plan projection (A1), submission history (C), delayed cleanup (D)."""
import json
import os
import time
from pathlib import Path

import pytest

from backend.dsh_plan import project, failed_step
from test_dsh_payment_findings import client, submit, reply, run_script, findings, slot, q, DOC  # noqa: F401

CANDS = {'payment': ['clause-1', 'clause-2', 'clause-3', 'clause-4'], 'exception': ['clause-4']}


def statuses(plan):
    return {s['step_id']: s['status'] for s in plan['steps']}


# ---------- pure projection ----------

def test_projection_partial_does_not_block_submission_and_is_recomputed():
    plan = project(CANDS, {'clause-1', 'clause-2', 'clause-3'}, {'submissions': 0, 'accepted': False})
    assert statuses(plan) == {'S1': 'partial', 'S2': 'pending', 'S3': 'pending', 'S4': 'pending'}
    assert plan['steps'][1]['missing_ids'] == ['clause-4']
    accepted = project(CANDS, {'clause-1', 'clause-2', 'clause-3'}, {'submissions': 1, 'accepted': True})
    assert statuses(accepted)['S3'] == 'done' and statuses(accepted)['S4'] == 'ready'   # partial S1/S2 do not block
    rejected_later = project(CANDS, {'clause-1'}, {'submissions': 2, 'accepted': False, 'last_codes': ['CLAIM_VALUE_NOT_IN_QUOTE']})
    assert statuses(rejected_later)['S3'] == 'blocked' and statuses(rejected_later)['S4'] == 'pending'
    assert rejected_later['steps'][2]['error_codes'] == ['CLAIM_VALUE_NOT_IN_QUOTE']


def test_projection_not_applicable_and_failed_step():
    plan = project({'payment': ['clause-1'], 'exception': []}, {'clause-1'}, {'submissions': 0})
    assert statuses(plan)['S2'] == 'not_applicable'
    assert failed_step(plan) == 'S3'
    assert failed_step(project({'payment': ['clause-1'], 'exception': []}, {'clause-1'},
                               {'submissions': 1, 'accepted': True}, published=True)) is None


# ---------- wired into the DSH loop ----------

def plan_events(rt, ident):
    return [e for e in rt.store.events(ident) if e['event_type'] in ('dsh.plan.created', 'dsh.plan.step')]


def test_plan_persisted_before_first_model_request_and_visible_in_detail(client):
    ident = submit(client)
    rt = client.app.state.service.dsh
    seen_at_first_call = []
    async def provider(payload, limit):
        if not seen_at_first_call:
            seen_at_first_call.append([e['event_type'] for e in rt.store.events(ident)])
        results = [json.loads(m['content']) for m in payload['messages'] if m['role'] == 'tool']
        if not results:
            return reply(calls=[('search_document', {'query': '付款'})])
        return reply('结束')
    rt.send_probe = provider
    rt.execute(ident)
    assert 'dsh.plan.created' in seen_at_first_call[0]
    detail = client.get('/api/local/dsh/runs/' + ident).json()
    assert statuses(detail['plan']) == {'S1': 'partial', 'S2': 'pending', 'S3': 'pending', 'S4': 'pending'}
    failed = next(e['data'] for e in rt.store.events(ident) if e['event_type'] == 'run.failed')
    assert failed['error_code'] == 'DSH_FINDINGS_MISSING' and failed['failed_step'] == 'S1'
    # plan events carry platform titles and clause IDs only, never document text
    assert '验收合格后30天' not in json.dumps([e['data'] for e in plan_events(rt, ident)], ensure_ascii=False)


def test_s3_returns_to_blocked_when_a_later_submission_fails_and_nothing_publishes(client):
    ident = submit(client)
    def script(n, results):
        if n == 1:
            return reply(calls=[('search_document', {'query': '付款'}), ('search_document', {'query': '付款', 'offset': 3})])
        if n == 2:
            return reply(calls=[('submit_findings', findings())])          # accepted
        if n == 3:
            return reply(calls=[('submit_findings', findings('验收合格后300天内付款'))])  # rejected replacement
        return reply('完成')
    rt, detail, _ = run_script(client, ident, script)
    assert detail['run']['exit_reason'] == 'DSH_FINDINGS_MISSING' and detail['artifacts'] == []
    assert statuses(detail['plan'])['S3'] == 'blocked' and statuses(detail['plan'])['S4'] == 'pending'
    checks = [e['data'] for e in rt.store.events(ident) if e['event_type'] == 'dsh.findings.checked']
    assert [(c['submission_number'], c['accepted']) for c in checks] == [(1, True), (2, False)]
    assert all(len(c['content_sha256']) == 64 for c in checks)


def test_published_record_lists_submission_history_and_plan_status(client):
    ident = submit(client)
    def script(n, results):
        if n == 1:
            return reply(calls=[('read_clause', {'clause_id': 'clause-1'})])
        if n == 2:
            return reply(calls=[('submit_findings', findings('验收合格后300天内付款'))])   # rejected
        if n == 3:
            return reply(calls=[('submit_findings', findings())])                          # coverage gap warning
        if n == 4:
            return reply(calls=[('read_clause', {'clause_id': 'clause-4'})])
        if n == 5:
            return reply(calls=[('submit_findings', findings(exception=slot(
                'supported', '质量争议时甲方可暂停付款', [q('clause-4', '发生质量争议时，甲方可暂停付款')])))])
        return reply('完成')
    rt, detail, _ = run_script(client, ident, script)
    assert detail['run']['status'] == 'succeeded', detail['run']
    record = json.loads(rt.store.db.execute('SELECT body FROM artifacts WHERE id=?', (next(
        a['id'] for a in detail['artifacts'] if a['name'] == 'dsh-findings.json'),)).fetchone()[0])
    hist = [(h['number'], h['accepted'], h['error_codes'], h['superseded_by']) for h in record['submissions']]
    assert hist == [(1, False, ['CLAIM_VALUE_NOT_IN_QUOTE'], 2), (2, False, ['COVERAGE_GAP'], 3), (3, True, [], None)]
    assert record['submission_number'] == 3
    succeeded = next(e['data'] for e in rt.store.events(ident) if e['event_type'] == 'run.succeeded')
    assert succeeded['plan_status']['S3'] == 'done' and succeeded['plan_status']['S4'] == 'done'
    assert len(record['submissions']) == 3 and all('claim' not in h for h in record['submissions'])


def test_model_text_cannot_mark_a_step_done(client):
    ident = submit(client)
    def script(n, results):
        if n == 1:
            return reply('S1 已完成，S2 已完成，S3 已完成。', calls=[('read_clause', {'clause_id': 'clause-1'})])
        return reply('全部完成')
    rt, detail, _ = run_script(client, ident, script)
    assert statuses(detail['plan'])['S2'] == 'pending' and statuses(detail['plan'])['S3'] == 'pending'


def test_free_template_has_no_plan(client):
    ident = submit(client, template='free', document='第1条 付款\n验收后30天付款。')
    rt, detail, _ = run_script(client, ident, lambda n, r: reply(calls=[('read_clause', {'clause_id': 'clause-1'})])
                               if n == 1 else reply('见 clause-1'))
    assert detail['run']['status'] == 'succeeded' and detail['plan'] is None


# ---------- D: delayed cleanup retry ----------

def test_pending_workspace_is_cleaned_by_delayed_retry(client, monkeypatch):
    from adapters.dsh_workspace import OwnedWorkspace
    rt = client.app.state.service.dsh
    root = Path(os.environ['HARNESS_DSH_RUN_ROOT'])
    held = OwnedWorkspace(root)            # lease held => cleanup must stay pending
    (held.path / 'secret.txt').write_text('SYNTH_PENDING_79')
    rt.cleanup_retry_seconds = 0.2
    rt.recover()
    assert rt.cleanup_status['pending'] == 1 and held.path.exists()
    import os as _os
    _os.close(held.lease)                   # holder exits
    for _ in range(50):
        if not held.path.exists():
            break
        time.sleep(0.1)
    assert not held.path.exists()
    assert rt.cleanup_status['pending'] == 0 and rt.cleanup_status['cleaned'] >= 1 and rt.cleanup_status['retries'] >= 1


def test_delayed_retry_is_bounded(client):
    from adapters.dsh_workspace import OwnedWorkspace
    rt = client.app.state.service.dsh
    held = OwnedWorkspace(Path(os.environ['HARNESS_DSH_RUN_ROOT']))
    rt.cleanup_retry_seconds, rt.cleanup_retry_limit = 0.05, 3
    rt.recover()
    for _ in range(100):  # wait until retries reach the limit (timers can be delayed under load)
        if rt.cleanup_status['retries'] >= 3:
            break
        time.sleep(0.05)
    time.sleep(0.5)       # an unbounded retry would keep counting past the limit
    assert rt.cleanup_status['retries'] == 3 and rt.cleanup_status['pending'] == 1 and held.path.exists()
    import os as _os
    _os.close(held.lease)
