"""HA-0099: a well-formed but non-existent clause ID is a bounded, correctable observation."""
import json

from test_dsh_payment_findings import client, submit, reply, run_script, findings, tool_results  # noqa: F401


def test_hallucinated_clause_returns_hint_and_run_recovers(client):
    ident = submit(client)
    def script(n, results):
        if n == 1:
            return reply(calls=[('read_clause', {'clause_id': 'clause-999'})])
        if n == 2:
            return reply(calls=[('search_document', {'query': '付款'}), ('search_document', {'query': '付款', 'offset': 3})])
        if n == 3:
            return reply(calls=[('submit_findings', findings())])
        return reply('完成')
    rt, detail, calls = run_script(client, ident, script)
    assert detail['run']['status'] == 'succeeded', detail['run']
    observation = tool_results(calls[1])[0]
    assert observation['error'] == 'CLAUSE_NOT_FOUND' and observation['matches'] == []
    assert 'clause-1 到 clause-4' in observation['hint']
    tool = [e['data'] for e in rt.store.events(ident) if e['event_type'] == 'dsh.tool.completed'][0]
    assert tool['error_code'] == 'CLAUSE_NOT_FOUND' and tool['new_evidence'] == 0 and tool['clause_ids'] == []
    assert detail['budget']['calls'] == 4                      # no hidden retry


def test_soft_errors_are_bounded(client):
    ident = submit(client)
    def script(n, results):
        return reply(calls=[('read_clause', {'clause_id': f'clause-{900 + n}'})]) if n <= 3 else reply('完成')
    rt, detail, calls = run_script(client, ident, script)
    assert detail['run']['status'] == 'failed' and detail['run']['exit_reason'] == 'DSH_CLAUSE_NOT_FOUND'
    soft = [e for e in rt.store.events(ident) if e['event_type'] == 'dsh.tool.completed']
    assert len(soft) == 2 and len(calls) == 3


def test_soft_error_does_not_count_as_progress(client):
    ident = submit(client)
    def script(n, results):
        return reply(calls=[('read_clause', {'clause_id': 'clause-1'})]) if n == 1 else \
            reply(calls=[('read_clause', {'clause_id': f'clause-{900 + n}'})]) if n <= 3 else reply('完成')
    rt, detail, _ = run_script(client, ident, script)
    soft = [e['data'] for e in rt.store.events(ident) if e['event_type'] == 'dsh.tool.completed' and e['data'].get('error_code')]
    assert len(soft) == 2 and all(s['new_evidence'] == 0 for s in soft)
