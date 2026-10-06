"""HA-0095: failure point is not the earliest unfinished step (jikesummary Replan下)."""
from backend.dsh_plan import project, failure_point, failed_step
from test_dsh_payment_findings import client, submit, reply, run_script, findings  # noqa: F401

CANDS = {'payment': ['clause-1', 'clause-2', 'clause-3', 'clause-4'], 'exception': ['clause-4']}


def test_pure_mapping_order():
    partial_rejected = project(CANDS, {'clause-1'}, {'submissions': 3, 'accepted': False, 'last_codes': ['QUOTES_INVALID']})
    assert failed_step(partial_rejected) == 'S1'
    assert failure_point(partial_rejected, 'DSH_FINDINGS_INVALID') == 'S3'
    assert failure_point(partial_rejected, 'TIMEOUT') == 'S3'            # blocked step wins over partial S1
    untouched = project(CANDS, set(), {'submissions': 0})
    assert failure_point(untouched, 'DSH_PROVIDER_TIMEOUT') == 'S1'     # nothing blocked: earliest unfinished
    assert failure_point(untouched, 'DSH_FINDINGS_MISSING') == 'S3'
    assert failure_point(None, 'TIMEOUT') is None


def test_partial_evidence_then_repeated_rejection_points_at_s3(client):
    ident = submit(client)
    def script(n, results):
        if n == 1:
            return reply(calls=[('read_clause', {'clause_id': 'clause-1'})])
        return reply(calls=[('submit_findings', findings('验收合格后300天内付款'))])
    rt, detail, _ = run_script(client, ident, script)
    failed = next(e['data'] for e in rt.store.events(ident) if e['event_type'] == 'run.failed')
    assert failed['error_code'] == 'DSH_FINDINGS_INVALID'
    assert failed['failed_step'] == 'S1' and failed['failure_point'] == 'S3', failed


def test_search_only_then_no_submission_points_at_s3(client):
    ident = submit(client)
    rt, detail, _ = run_script(client, ident, lambda n, r: reply(calls=[('search_document', {'query': '付款'})])
                               if n == 1 else reply('结束'))
    failed = next(e['data'] for e in rt.store.events(ident) if e['event_type'] == 'run.failed')
    assert failed['error_code'] == 'DSH_FINDINGS_MISSING'
    assert failed['failed_step'] == 'S1' and failed['failure_point'] == 'S3'
