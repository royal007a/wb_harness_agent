"""HA-0114: read-only per-turn decision path (metadata only)."""
import json

from test_dsh_payment_findings import client, submit, reply, run_script, findings  # noqa: F401


def test_trace_groups_actions_by_turn_and_has_no_text(client):
    ident = submit(client, document='第1条 付款\nSYNTH_TRACE_SECRET 甲方应在验收合格后30天内向乙方支付合同款。\n'
                                    '第2条 付款\n付款前开具发票。\n第3条 付款例外\n发生质量争议时，甲方可暂停付款。')
    def script(n, results):
        if n == 1:
            return reply(calls=[('read_clause', {'clause_id': 'clause-999'}), ('search_document', {'query': '付款'})])
        if n == 2:
            return reply(calls=[('submit_findings', findings('验收合格后300天内付款'))])
        if n == 3:
            return reply(calls=[('read_clause', {'clause_id': 'clause-3'}), ('submit_findings', findings())])
        return reply('完成')
    rt, detail, _ = run_script(client, ident, script)
    before = rt.store.db.total_changes
    response = client.get(f'/api/local/dsh/runs/{ident}/trace')
    assert response.status_code == 200 and rt.store.db.total_changes == before       # GET writes nothing
    trace = response.json()
    assert trace['trace_version'] == 'dsh-trace@1' and trace['versions']['plan_version'] == 'dsh-plan@1'
    turns = trace['turns']
    assert [t['turn'] for t in turns] == list(range(1, len(turns) + 1))
    first = turns[0]['actions']
    assert first[0]['kind'] == 'tool' and first[0]['error_code'] == 'CLAUSE_NOT_FOUND'
    assert first[1]['tool'] == 'search_document' and first[1]['total_matches'] >= 1
    assert turns[1]['actions'][0] == {'kind': 'findings', 'accepted': False, 'submission_number': 1,
                                      'error_codes': turns[1]['actions'][0]['error_codes']}
    assert all(t['model'] and type(t['model']['latency_ms']) is int for t in turns)
    assert turns[0]['plan_after'] and trace['outcome']['event'] in ('run.succeeded', 'run.failed')
    assert 'SYNTH_TRACE_SECRET' not in json.dumps(trace, ensure_ascii=False)
    assert '验收合格' not in json.dumps(trace, ensure_ascii=False)


def test_trace_404_for_unknown_run(client):
    assert client.get('/api/local/dsh/runs/run_nope/trace').status_code == 404
