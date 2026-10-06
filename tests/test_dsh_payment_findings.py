"""HA-0079: payment-terms findings verification, coverage and no-progress stop.

Unit tests exercise the pure verifier. Integration tests run the official DSH SDK
subprocess with a synthetic Provider (control logic only; not model quality).
"""
import json

import pytest
from fastapi.testclient import TestClient

from backend.app import create_app
from backend.dsh_findings import verify
from backend.dsh_provider import parse_response

CLAUSES = {
    'clause-1': '第1条 付款\n甲方应在验收合格后30天内向乙方支付合同款。',
    'clause-2': '第2条 发票\n乙方应在付款前10个工作日内开具发票。',
    'clause-3': '第3条 例外\n发生质量争议时，甲方可暂停付款直至争议解决。',
    'clause-4': '第4条 其他\n本合同一式两份。',
}
SEEN = {'clause-1', 'clause-2', 'clause-3'}


def slot(status='unknown', claim='', quotes=()):
    return {'status': status, 'claim': claim, 'quotes': list(quotes)}


def q(ident, text):
    return {'clause_id': ident, 'text': text}


def good(**changes):
    value = {'term': slot('supported', '验收合格后30天内付款', [q('clause-1', '验收合格后30天内向乙方支付合同款')]),
             'trigger': slot('supported', '验收合格', [q('clause-1', '甲方应在验收合格后')]),
             'exception': slot('supported', '质量争议时甲方可暂停付款', [q('clause-3', '发生质量争议时，甲方可暂停付款')]),
             'conflict': slot('unknown')}
    value.update(changes)
    return value


def codes(result):
    return {e['code'] for e in result['errors']}


# ---------- pure verifier ----------

def test_valid_findings_are_mechanically_checked_but_conflict_unknown_is_partial():
    result = verify(good(), CLAUSES, SEEN)
    assert result['errors'] == []
    assert result['business_status'] == 'partial'  # conflict slot is unknown
    full = verify(good(conflict=slot('supported', '无冲突约定', [q('clause-4', '本合同一式两份')])),
                  CLAUSES, SEEN | {'clause-4'})
    assert full['business_status'] == 'mechanically_checked'


@pytest.mark.parametrize('claim,quote,code', [
    ('验收合格后300天内付款', '验收合格后30天内向乙方支付合同款', 'CLAIM_VALUE_NOT_IN_QUOTE'),     # 30 -> 300
    ('验收合格后30个工作日内付款', '验收合格后30天内向乙方支付合同款', 'CLAIM_VALUE_NOT_IN_QUOTE'),  # unit
    ('验收合格后三十天内付款', '验收合格后30天内向乙方支付合同款', None),                          # CN numeral ok
    ('验收合格后三百天内付款', '验收合格后30天内向乙方支付合同款', 'CLAIM_VALUE_NOT_IN_QUOTE'),
    ('乙方应在验收后30天内付款', '验收合格后30天内向乙方支付合同款', None),                        # party present
    ('丙方应在验收后30天内付款', '验收合格后30天内向乙方支付合同款', 'CLAIM_PARTY_NOT_IN_QUOTE'),
    ('验收合格后30天内付款', '验收合格后30日内向乙方支付合同款', 'QUOTE_NOT_IN_SOURCE'),          # altered quote
])
def test_values_units_parties_and_literal_quotes(claim, quote, code):
    result = verify(good(term=slot('supported', claim, [q('clause-1', quote)])), CLAUSES, SEEN)
    assert (codes(result) == {code}) if code else result['errors'] == []


def test_unread_or_foreign_clause_cannot_be_cited():
    # clause-4 exists but was not returned in this Run; clause-99 belongs to no document.
    for ident in ('clause-4', 'clause-99'):
        result = verify(good(conflict=slot('supported', '一式两份', [q(ident, '本合同一式两份')])), CLAUSES, SEEN)
        assert codes(result) == {'QUOTE_CLAUSE_NOT_READ'}


@pytest.mark.parametrize('mutate,code', [
    (lambda v: v.pop('exception'), 'SLOT_MISSING_OR_INVALID'),
    (lambda v: v.update(term=slot('supported', '30天', [])), 'SUPPORTED_WITHOUT_EVIDENCE'),
    (lambda v: v.update(conflict=slot('unknown', '', [q('clause-1', '验收合格后')])), 'UNKNOWN_WITH_QUOTES'),
    (lambda v: v.update(conflict=slot('conflicting', '冲突', [q('clause-1', '验收合格后')])), 'CONFLICT_NEEDS_TWO_SOURCES'),
    (lambda v: v.update(term={'status': 'supported', 'claim': 'x', 'quotes': 'clause-1'}), 'QUOTES_INVALID'),
    (lambda v: v.update(extra='x'), 'SUBMISSION_INVALID'),
    (lambda v: v.update(gaps=['x' * 201]), 'GAPS_INVALID'),
])
def test_structural_negatives(mutate, code):
    value = good()
    mutate(value)
    assert code in codes(verify(value, CLAUSES, SEEN))


def test_conflicting_needs_two_distinct_read_sources():
    result = verify(good(conflict=slot('conflicting', '期限冲突',
        [q('clause-1', '30天内'), q('clause-2', '10个工作日内')])), CLAUSES, SEEN)
    assert result['errors'] == [] and result['business_status'] == 'conflicting'


def test_unread_exception_candidate_is_reported_not_silently_complete():
    result = verify(good(exception=slot('unknown')), CLAUSES, {'clause-1', 'clause-2'})
    assert result['errors'] == []
    assert result['platform_gaps'] == [{'code': 'EXCEPTION_CANDIDATES_UNREAD', 'clause_ids': ['clause-3']}]
    assert result['business_status'] == 'partial'


def test_read_exception_left_unknown_is_reported():
    result = verify(good(exception=slot('unknown')), CLAUSES, SEEN)
    assert result['platform_gaps'] == [{'code': 'EXCEPTION_CANDIDATE_NOT_REPORTED', 'clause_ids': ['clause-3']}]
    assert result['business_status'] == 'partial'


def test_negation_change_is_not_mechanically_detectable():
    """Documented limit: literal quote + matching values does not prove the claim."""
    result = verify(good(exception=slot('supported', '质量争议时甲方不得暂停付款',
                                        [q('clause-3', '发生质量争议时，甲方可暂停付款')])), CLAUSES, SEEN)
    assert result['errors'] == []  # passes mechanics; semantics remain human review


def test_error_codes_never_echo_model_text():
    secret = 'SYNTH_FINDINGS_SECRET_79'
    result = verify(good(term=slot('supported', secret + '300天', [q('clause-1', secret)])), CLAUSES, SEEN)
    assert secret not in json.dumps(result['errors'])


# ---------- official DSH SDK + synthetic Provider ----------

@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv('HARNESS_DSH_LOCAL', 'enabled')
    monkeypatch.setenv('HARNESS_DSH_RUN_ROOT', str(tmp_path / 'owned'))
    monkeypatch.delenv('HARNESS_DSH_REAL_ENABLED', raising=False)
    monkeypatch.delenv('HARNESS_DSH_CREDENTIAL_REF', raising=False)
    from backend.agent_runtime import KeyringCredentialResolver
    monkeypatch.setattr(KeyringCredentialResolver, 'resolve', lambda *a: pytest.fail('no credentials'))
    with TestClient(create_app(tmp_path / 't.db', run_worker=False), base_url='http://localhost') as value:
        yield value


DOC = ('第1条 付款\n甲方应在验收合格后30天内向乙方支付合同款。\n'
       '第2条 付款方式\n付款通过银行转账。\n'
       '第3条 付款发票\n乙方应在付款前开具发票。\n'
       '第4条 付款例外\n发生质量争议时，甲方可暂停付款直至争议解决。')


def submit(client, template='payment_terms', document=DOC, key='k', **extra):
    body = {'objective': '核对付款条件，引用证据块。', 'document': document, 'mode': 'integration_probe',
            'public_data_confirmed': True, 'template': template, **extra}
    response = client.post('/api/local/dsh/runs', json=body, headers={'Idempotency-Key': key})
    assert response.status_code == 201, response.text
    return response.json()['initial_run']['id']


def reply(text='', calls=()):
    message = {'content': text}
    if calls:
        message['tool_calls'] = [{'id': f'c{i}', 'type': 'function', 'function': {
            'name': name, 'arguments': json.dumps(args, ensure_ascii=False)}} for i, (name, args) in enumerate(calls)]
    return parse_response({'choices': [{'finish_reason': 'tool_calls' if calls else 'stop', 'message': message}],
                           'usage': {'prompt_tokens': 10, 'completion_tokens': 10, 'total_tokens': 20}})


def tool_results(payload):
    return [json.loads(m['content']) for m in payload['messages'] if m['role'] == 'tool']


def findings(term_claim='验收合格后30天内付款', exception=None):
    return {'term': slot('supported', term_claim, [q('clause-1', '验收合格后30天内向乙方支付合同款')]),
            'trigger': slot('supported', '验收合格', [q('clause-1', '甲方应在验收合格后')]),
            'exception': exception or slot('unknown'), 'conflict': slot('unknown')}


def run_script(client, ident, script):
    rt = client.app.state.service.dsh
    calls = []
    async def provider(payload, limit):
        calls.append(payload)
        return script(len(calls), tool_results(payload))
    rt.send_probe = provider
    rt.execute(ident)
    return rt, rt.detail(ident), calls


def artifact(rt, detail, name):
    item = next(a for a in detail['artifacts'] if a['name'] == name)
    return rt.store.db.execute('SELECT body FROM artifacts WHERE id=?', (item['id'],)).fetchone()[0].decode()


def test_old_probe1_inverted_300_days_cannot_become_verified_result(client):
    ident = submit(client)
    def script(n, results):
        if n == 1:
            return reply(calls=[('read_clause', {'clause_id': 'clause-1'})])
        if n <= 4:  # keeps submitting the wrong value; each attempt costs a model call
            return reply(calls=[('submit_findings', findings('验收合格后300天内付款'))])
        return reply('付款期限为验收后300天，依据 clause-1。')
    rt, detail, calls = run_script(client, ident, script)
    assert detail['run']['status'] == 'failed'
    assert detail['run']['exit_reason'] == 'DSH_FINDINGS_INVALID'
    assert detail['artifacts'] == []
    assert len(calls) == detail['budget']['calls'] == 4  # corrections are on the same ledger
    events = rt.store.events(ident)
    rejected = [e['data'] for e in events if e['event_type'] == 'dsh.findings.checked']
    assert [e['error_codes'] for e in rejected] == [['CLAIM_VALUE_NOT_IN_QUOTE']] * 3
    assert '300天' not in json.dumps(events, ensure_ascii=False)


def test_correction_after_rejection_publishes_checked_findings(client):
    ident = submit(client)
    def script(n, results):
        if n == 1:
            return reply(calls=[('search_document', {'query': '付款'})])
        if n == 2:
            assert results[-1]['total'] == 4 and results[-1]['truncated'] and results[-1]['next_offset'] == 3
            return reply(calls=[('search_document', {'query': '付款', 'offset': 3})])
        if n == 3:
            assert [m['clause_id'] for m in results[-1]['matches']] == ['clause-4']
            return reply(calls=[('submit_findings', findings('验收合格后300天内付款'))])
        if n == 4:
            assert results[-1]['accepted'] is False
            return reply(calls=[('submit_findings', findings(exception=slot(
                'supported', '质量争议时甲方可暂停付款', [q('clause-4', '发生质量争议时，甲方可暂停付款')])))])
        assert results[-1]['accepted'] is True
        return reply('付款：验收后30天（clause-1）；质量争议可暂停（clause-4）。')
    rt, detail, calls = run_script(client, ident, script)
    assert detail['run']['status'] == 'succeeded', detail['run']
    record = json.loads(artifact(rt, detail, 'dsh-findings.json'))
    assert record['business_status'] == 'partial'  # conflict slot unknown
    assert record['platform_gaps'] == []
    assert record['findings']['term']['claim'] == '验收合格后30天内付款'
    assert record['human_review_required'] is True
    assert 'semantics_not_verified' in record['verification']
    succeeded = next(e['data'] for e in rt.store.events(ident) if e['event_type'] == 'run.succeeded')
    assert succeeded['business_status'] == 'partial' and succeeded['template'] == 'payment_terms'


def test_old_probe3_inverted_fourth_exception_is_found_or_reported(client):
    ident = submit(client)
    def script(n, results):
        if n == 1:
            return reply(calls=[('search_document', {'query': '付款'})])
        if n in (2, 3):  # ignores pagination and submits twice anyway
            return reply(calls=[('submit_findings', findings())])
        return reply('付款需验收后30天，依据 clause-1。')
    rt, detail, _ = run_script(client, ident, script)
    assert detail['run']['status'] == 'succeeded'
    record = json.loads(artifact(rt, detail, 'dsh-findings.json'))
    assert record['platform_gaps'] == [{'code': 'EXCEPTION_CANDIDATES_UNREAD', 'clause_ids': ['clause-4']}]
    assert record['business_status'] == 'partial'
    checks = [e['data'] for e in rt.store.events(ident) if e['event_type'] == 'dsh.findings.checked']
    assert checks[0]['error_codes'] == ['COVERAGE_GAP'] and checks[1]['accepted'] is True


def test_old_probe2_inverted_repeated_read_stops_early(client):
    ident = submit(client, template='free')
    rt, detail, calls = run_script(client, ident, lambda n, r: reply(calls=[('read_clause', {'clause_id': 'clause-1'})]))
    assert detail['run']['exit_reason'] == 'DSH_NO_PROGRESS'
    assert len(calls) == detail['budget']['calls'] == 3  # was 8 at the hard cap
    assert detail['artifacts'] == []
    tools = [e['data'] for e in rt.store.events(ident) if e['event_type'] == 'dsh.tool.completed']
    assert [t['repeated_action'] for t in tools] == [False, True, True]
    stopped = [e['data'] for e in rt.store.events(ident) if e['event_type'] == 'dsh.progress.stopped']
    assert stopped == [{'no_progress_turns': 2, 'repeat_turns': 2}]  # judged before a 4th request


def test_legitimate_search_then_reads_are_not_stopped(client):
    ident = submit(client, template='free')
    def script(n, results):
        if n == 1:
            return reply(calls=[('search_document', {'query': '付款'})])
        if n <= 4:  # reads already-returned clauses: no new evidence but not identical actions
            return reply(calls=[('read_clause', {'clause_id': f'clause-{n - 1}'})])
        return reply('依据 clause-1，验收后30天付款。')
    rt, detail, calls = run_script(client, ident, script)
    assert detail['run']['status'] == 'succeeded', detail['run']
    assert len(calls) == 5


def test_four_consecutive_actions_without_new_evidence_stop(client):
    ident = submit(client, template='free')
    def script(n, results):
        if n == 1:
            return reply(calls=[('read_clause', {'clause_id': 'clause-1'})])
        return reply(calls=[('search_document', {'query': f'验收{"合格" * (n - 1)}'[:3 + n]})])
    rt, detail, calls = run_script(client, ident, script)
    assert detail['run']['exit_reason'] == 'DSH_NO_PROGRESS'
    assert len(calls) <= 6


def test_payment_template_without_findings_is_not_published(client):
    ident = submit(client)
    def script(n, results):
        if n == 1:
            return reply(calls=[('read_clause', {'clause_id': 'clause-1'})])
        return reply('依据 clause-1，验收后30天付款。')
    _, detail, _ = run_script(client, ident, script)
    assert detail['run']['exit_reason'] == 'DSH_FINDINGS_MISSING' and detail['artifacts'] == []


def test_findings_tool_not_offered_on_free_template(client):
    ident = submit(client, template='free')
    def script(n, results):
        return reply(calls=[('submit_findings', findings())])
    _, detail, _ = run_script(client, ident, script)
    assert detail['run']['status'] == 'failed'
    assert detail['run']['exit_reason'] in {'DSH_TOOL_POLICY', 'DSH_RUNTIME_FAILED'}


def test_free_template_keeps_previous_draft_boundary(client):
    """Unchanged by design: free-form runs still publish citation-valid drafts for human review."""
    ident = submit(client, template='free', document='第1条 付款\n验收后30天付款。')
    def script(n, results):
        if n == 1:
            return reply(calls=[('read_clause', {'clause_id': 'clause-1'})])
        return reply('依据 clause-1，付款期限为验收后300天。')
    rt, detail, _ = run_script(client, ident, script)
    assert detail['run']['status'] == 'succeeded'
    assert not any(a['name'] == 'dsh-findings.json' for a in detail['artifacts'])


def test_budget_exhaustion_wins_over_correction_loop(client):
    def script(n, results):
        if n == 1:
            return reply(calls=[('read_clause', {'clause_id': 'clause-1'})])
        return reply(calls=[('submit_findings', findings('验收合格后300天内付款'))])
    # Measure the real per-call reservations once, then set the limit so call 3 cannot be reserved.
    probe = submit(client, key='measure')
    rt, _, _ = run_script(client, probe, script)
    rows = rt.store.db.execute('SELECT call_id, input_bound + output_limit, input_tokens + output_tokens '
                               'FROM business_budget_calls WHERE root_id=? ORDER BY call_id', (probe,)).fetchall()
    bounds = {call: (bound, used) for call, bound, used in rows}
    spent_two = bounds['call_1'][1] + bounds['call_2'][1]
    ident = submit(client, key='limited', token_limit=spent_two + bounds['call_3'][0] - 1)
    rt, detail, calls = run_script(client, ident, script)
    assert detail['run']['exit_reason'] == 'BUSINESS_TOKEN_BUDGET_EXHAUSTED', detail['run']
    assert len(calls) == detail['budget']['calls'] == 2  # the 3rd (a correction) was never sent
    assert detail['budget']['reserved'] == 0 and detail['artifacts'] == []


def test_findings_text_never_enters_events(client):
    secret = 'SYNTH_EVENT_SECRET_79'
    ident = submit(client)
    def script(n, results):
        if n == 1:
            return reply(calls=[('read_clause', {'clause_id': 'clause-1'})])
        if n == 2:
            return reply(calls=[('submit_findings', findings(secret + '验收合格后30天内付款'))])
        if n == 3:
            return reply(calls=[('read_clause', {'clause_id': 'clause-4'})])
        if n == 4:
            return reply(calls=[('submit_findings', findings(exception=slot('unknown', secret)))])
        return reply('完成 clause-1')
    rt, detail, _ = run_script(client, ident, script)
    assert detail['run']['status'] == 'succeeded', detail['run']
    assert secret not in json.dumps(rt.store.events(ident), ensure_ascii=False)


# ---- HA-0080: patterns observed with real doubao ----

def test_real_pattern_search_then_first_reads_of_all_hits_not_stopped(client):
    """doubao searched, then read every hit in full: first reads are new evidence."""
    ident = submit(client, template='free', document=DOC)
    def script(n, results):
        if n == 1:
            return reply(calls=[('search_document', {'query': '付款'}), ('search_document', {'query': '例外'}),
                                ('search_document', {'query': '争议'})])
        if n == 2:
            return reply(calls=[('read_clause', {'clause_id': f'clause-{i}'}) for i in range(1, 5)])
        return reply('付款 30 天，见 clause-1。')
    rt, detail, calls = run_script(client, ident, script)
    assert detail['run']['status'] == 'succeeded', detail['run']


def test_real_pattern_five_parallel_reads_in_one_turn_accepted(client):
    document = '\n'.join(f'第{i}条 付款{i}\n内容{i}。' for i in range(1, 7))
    ident = submit(client, template='free', document=document)
    def script(n, results):
        if n == 1:
            return reply(calls=[('read_clause', {'clause_id': f'clause-{i}'}) for i in range(1, 6)])
        return reply('见 clause-1。')
    _, detail, _ = run_script(client, ident, script)
    assert detail['run']['status'] == 'succeeded', detail['run']


def test_rereading_already_read_clauses_still_stops(client):
    ident = submit(client, template='free', document=DOC)
    def script(n, results):
        if n == 1:
            return reply(calls=[('read_clause', {'clause_id': 'clause-1'})])
        return reply(calls=[('read_clause', {'clause_id': f'clause-{1 + (n % 2)}'})])  # alternate 2,1,2,1
    _, detail, calls = run_script(client, ident, script)
    assert detail['run']['exit_reason'] == 'DSH_NO_PROGRESS' and len(calls) < 8


def test_real_pattern_parallel_searches_in_one_turn_are_one_progressing_turn(client):
    """doubao issued 5 different searches in its first turn; most returned nothing new."""
    ident = submit(client, template='free', document=DOC)
    def script(n, results):
        if n == 1:
            return reply(calls=[('search_document', {'query': q}) for q in ('付款', '支付', '例外', '暂停', '争议')])
        return reply('付款 30 天，见 clause-1。')
    _, detail, calls = run_script(client, ident, script)
    assert detail['run']['status'] == 'succeeded', detail['run']
    assert len(calls) == 2
