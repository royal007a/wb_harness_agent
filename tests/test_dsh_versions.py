"""HA-0113: every Run records what it was decided with (jikesummary 全链路监控: promptVersion; 生成评审: ReviewReceipt)."""
import json

from test_dsh_payment_findings import client, submit, reply, run_script, findings, artifact  # noqa: F401


def script(n, results):
    if n == 1:
        return reply(calls=[('search_document', {'query': '付款'}), ('search_document', {'query': '付款', 'offset': 3})])
    if n == 2:
        return reply(calls=[('submit_findings', findings())])
    return reply('完成')


def versions_of(rt, ident):
    events = rt.store.events(ident)
    found = [e for e in events if e['event_type'] == 'dsh.run.versions']
    assert len(found) == 1
    first_model = next(e for e in events if e['event_type'] == 'dsh.context.assembled')
    assert found[0]['sequence'] < first_model['sequence']
    return found[0]['data']


def test_versions_recorded_before_first_model_call_and_in_findings(client):
    ident = submit(client, objective='SYNTH_OBJECTIVE_核对付款条件')
    rt, detail, _ = run_script(client, ident, script)
    data = versions_of(rt, ident)
    assert set(data) == {'release', 'prompt_sha256', 'tools', 'contract_sha256', 'validator_sha256', 'plan_version'}
    assert data['tools'] == ['read_clause', 'search_document', 'submit_findings'] and data['plan_version'] == 'dsh-plan@1'
    assert 'SYNTH_OBJECTIVE' not in json.dumps(data, ensure_ascii=False)
    succeeded = next(e['data'] for e in rt.store.events(ident) if e['event_type'] == 'run.succeeded')
    assert succeeded['versions'] == {k: data[k] for k in ('release', 'validator_sha256', 'plan_version')}
    assert 'versions' not in json.loads(artifact(rt, detail, 'dsh-findings.json'))   # old findings readers stay valid


def test_prompt_digest_changes_with_objective(client):
    a = submit(client, objective='核对付款条件A', key='a')
    rt, _, _ = run_script(client, a, script)
    b = submit(client, objective='核对付款条件B', key='b')
    rt, _, _ = run_script(client, b, script)
    va, vb = versions_of(rt, a), versions_of(rt, b)
    assert va['prompt_sha256'] != vb['prompt_sha256']
    assert va['validator_sha256'] == vb['validator_sha256'] and va['contract_sha256'] == vb['contract_sha256']
