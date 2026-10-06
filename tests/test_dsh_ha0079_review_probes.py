"""mymaccodex review probes for HA-0079 @ ebcb8fa, kept verbatim as regressions (fixed in the follow-up).

Source: ~/code/research/reviews/HA0079_ebcb8fa_review_probes.py. Only additions are marked below.
"""
import copy
import json

import pytest
from jsonschema import Draft202012Validator
from test_dsh_payment_findings import (client, submit, reply, run_script, artifact,
                                      findings, slot, q, good, CLAUSES, SEEN)
from backend.dsh_findings import verify

SHORT = '第1条 付款\n甲方应在验收合格后30天内向乙方支付合同款。'

def test_final_text_cannot_reintroduce_rejected_value(client):
    ident = submit(client, document=SHORT)
    def script(n, results):
        if n == 1:
            return reply(calls=[('read_clause', {'clause_id': 'clause-1'})])
        if n == 2:
            return reply(calls=[('submit_findings', findings())])
        assert results[-1]['accepted'] is True
        return reply('依据 clause-1，甲方应在验收合格后300天内付款。')
    rt, detail, calls = run_script(client, ident, script)
    print('FINAL', detail['run']['status'], len(calls))
    if detail['run']['status'] == 'succeeded':
        print('RECORD', json.loads(artifact(rt, detail, 'dsh-findings.json'))['findings']['term'])
        text = artifact(rt, detail, 'dsh-analysis.txt')
        print('PUBLISHED', text)
        assert '300天' not in text

def test_provider_tool_schema_is_valid_json_schema(client):
    ident = submit(client, document=SHORT)
    def script(n, results):
        if n == 1:
            return reply(calls=[('read_clause', {'clause_id': 'clause-1'})])
        if n == 2:
            return reply(calls=[('submit_findings', findings())])
        return reply('核对结果见 clause-1。')
    rt, detail, calls = run_script(client, ident, script)
    for tool in calls[0]['tools']:
        print('TOOL_SCHEMA', tool['function']['name'], json.dumps(tool['function']['parameters']))
        Draft202012Validator.check_schema(tool['function']['parameters'])

def test_conflicting_claim_cannot_bypass_value_check(client):
    document = SHORT + '\n第2条 付款\n乙方应在付款前10个工作日内开具发票。'
    ident = submit(client, document=document)
    bad = findings()
    bad['term'] = slot('conflicting', '甲方付款期限为300天或100个工作日，丙方负责',
                       [q('clause-1', '30天内'), q('clause-2', '10个工作日内')])
    def script(n, results):
        if n == 1:
            return reply(calls=[('search_document', {'query': '付款'})])
        if n == 2:
            return reply(calls=[('submit_findings', bad)])
        return reply('存在冲突，见 clause-1、clause-2。')
    rt, detail, calls = run_script(client, ident, script)
    print('CONFLICT', detail['run']['status'])
    if detail['run']['status'] == 'succeeded':
        print('RECORD', artifact(rt, detail, 'dsh-findings.json'))
    assert detail['run']['status'] != 'succeeded'

@pytest.mark.parametrize('claim', ['验收后3,030天付款', '验收后三千三十天付款'])
def test_numerical_suffix_not_mistaken_for_whole_value(claim):
    value = good(term=slot('supported', claim, [q('clause-1', '30天内')]))
    result = verify(value, CLAUSES, SEEN)
    print('NUMERIC', claim, result['errors'])
    assert result['errors']

def test_rejected_replacement_does_not_reuse_old_acceptance(client):
    ident = submit(client, document=SHORT)
    def script(n, results):
        if n == 1:
            return reply(calls=[('read_clause', {'clause_id': 'clause-1'})])
        if n == 2:
            return reply(calls=[('submit_findings', findings())])
        if n == 3:
            assert results[-1]['accepted'] is True
            return reply(calls=[('submit_findings', findings('验收后300天付款'))])
        assert results[-1]['accepted'] is False
        return reply('最后结果依据 clause-1。')
    rt, detail, calls = run_script(client, ident, script)
    print('STALE', detail['run']['status'], [e['data'] for e in rt.store.events(ident)
          if e['event_type'] == 'dsh.findings.checked'])
    assert detail['run']['status'] != 'succeeded'

def test_second_exception_read_but_not_reported_stays_gap():
    clauses = dict(CLAUSES, **{'clause-5': '第5条 付款例外\n发生交付争议时，乙方可延期支付货款。'})
    result = verify(good(), clauses, SEEN | {'clause-5'})
    print('MISSING_EXCEPTION', result['platform_gaps'])
    assert any('clause-5' in g['clause_ids'] for g in result['platform_gaps'])

def test_default_synthetic_payment_path_is_usable(client):
    ident = submit(client, document=SHORT)
    rt = client.app.state.service.dsh
    # Do not replace send_probe: this is exactly the public default mode.
    rt.execute(ident)
    detail = rt.detail(ident)
    print('DEFAULT_PROBE', detail['run']['status'], detail['run']['exit_reason'])
    assert detail['run']['status'] == 'succeeded'

def test_findings_publish_failure_rolls_back_both_artifacts(client, monkeypatch):
    ident = submit(client, document=SHORT)
    publisher = client.app.state.service.pi_contract_review
    original = publisher._publish
    def fail_after_findings(db, run, name, *args):
        result = original(db, run, name, *args)
        if name == 'dsh-findings.json':
            raise RuntimeError('SYNTH_PRIVATE_ROLLBACK_79')
        return result
    monkeypatch.setattr(publisher, '_publish', fail_after_findings)
    def script(n, results):
        if n == 1:
            return reply(calls=[('read_clause', {'clause_id': 'clause-1'})])
        if n == 2:
            return reply(calls=[('submit_findings', findings())])
        return reply('完成 clause-1。')
    rt, detail, calls = run_script(client, ident, script)
    assert detail['run']['status'] == 'failed'
    assert detail['artifacts'] == []
    assert 'SYNTH_PRIVATE_ROLLBACK_79' not in json.dumps(rt.store.events(ident))

def test_cancel_after_findings_wins_over_publication(client):
    ident = submit(client, document=SHORT)
    def script(n, results):
        if n == 1:
            return reply(calls=[('read_clause', {'clause_id': 'clause-1'})])
        if n == 2:
            return reply(calls=[('submit_findings', findings())])
        client.app.state.service.dsh.cancel(ident)
        return reply('完成 clause-1。')
    rt, detail, calls = run_script(client, ident, script)
    assert detail['run']['status'] == 'cancelled'
    assert detail['artifacts'] == []


# ---- additions by the author for the same findings ----

def test_published_text_is_rendered_from_verified_record(client):
    ident = submit(client, document=SHORT)
    def script(n, results):
        if n == 1:
            return reply(calls=[('read_clause', {'clause_id': 'clause-1'})])
        if n == 2:
            return reply(calls=[('submit_findings', findings())])
        return reply('依据 clause-1，甲方应在验收合格后300天内付款。')
    rt, detail, _ = run_script(client, ident, script)
    assert detail['run']['status'] == 'succeeded'
    text = artifact(rt, detail, 'dsh-analysis.txt')
    assert '300天' not in text and '验收合格后30天内付款' in text and '需人工复核' in text
    succeeded = next(e['data'] for e in rt.store.events(ident) if e['event_type'] == 'run.succeeded')
    assert succeeded['model_final_text_published'] is False and succeeded['submission_number'] == 1


@pytest.mark.parametrize('claim,quote,ok', [
    ('验收后3,030天付款', '验收后3,030天内付款', True),
    ('验收后三千三十天付款', '验收后3030天内付款', True),
    ('验收后30,60天付款', '验收后30天内付款', False),     # ambiguous numeral is rejected, not truncated
    ('验收后3千天付款', '验收后3000天内付款', False),
])
def test_whole_numeral_tokens(claim, quote, ok):
    clauses = dict(CLAUSES, **{'clause-9': '第9条 付款\n' + quote + '。'})
    result = verify(good(term=slot('supported', claim, [q('clause-9', quote)])), clauses, SEEN | {'clause-9'})
    assert (result['errors'] == []) is ok, result['errors']


@pytest.mark.parametrize('claim,code', [
    ('甲方付款期限为30天或10个工作日', None),
    ('甲方付款期限为300天或10个工作日', 'CLAIM_VALUE_NOT_IN_QUOTE'),
    ('甲方付款期限为30个工作日或10天', 'CLAIM_VALUE_NOT_IN_QUOTE'),
    ('丙方付款期限为30天或10个工作日', 'CLAIM_PARTY_NOT_IN_QUOTE'),
])
def test_conflicting_branch_runs_value_unit_party_checks(claim, code):
    value = good(conflict=slot('conflicting', claim, [q('clause-1', '甲方应在验收合格后30天内'),
                                                       q('clause-2', '10个工作日内')]))
    result = verify(value, CLAUSES, SEEN)
    assert ({e['code'] for e in result['errors']} == {code}) if code else result['errors'] == []


def test_default_synthetic_payment_path_publishes_partial_with_label(client):
    document = ('第1条 付款\n甲方应在验收合格后30天内付款。\n第2条 付款方式\n付款通过转账。\n'
                '第3条 付款发票\n付款前开具发票。\n第4条 付款例外\n发生质量争议时，甲方可暂停付款。')
    ident = submit(client, document=document)
    rt = client.app.state.service.dsh
    rt.execute(ident)  # built-in synthetic provider, not replaced
    detail = rt.detail(ident)
    assert detail['run']['status'] == 'succeeded', detail['run']
    record = json.loads(artifact(rt, detail, 'dsh-findings.json'))
    assert record['findings']['exception']['quotes'][0]['clause_id'] == 'clause-4'  # reached via pagination
    assert record['business_status'] == 'partial'
