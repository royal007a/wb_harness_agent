"""HA-0094: platform feedback survives context pressure (jikesummary 上下文分诊/语义压缩: errors are P0)."""
import json

from backend.dsh_context import assemble
from test_dsh_context import payload, turn, call, STATE
from test_dsh_payment_findings import client, submit, reply, run_script, findings  # noqa: F401

REJECTION = json.dumps({'accepted': False, 'submission_number': 1, 'errors': [
    {'code': 'CLAIM_VALUE_NOT_IN_QUOTE', 'slot': 'term', 'detail': 'SYNTH_DETAIL ' * 40}],
    'hint': '引文必须逐字摘自本轮读过的证据块。'}, ensure_ascii=False)


def rejection_turn():
    return [{'role': 'assistant', 'content': '', 'tool_calls': [call('f1', 'submit_findings', '{}')]},
            {'role': 'tool', 'tool_call_id': 'f1', 'content': REJECTION}]


def test_rejection_feedback_is_never_stubbed_under_budget_pressure():
    big = '付款条款内容。' * 400
    sent, report = assemble(payload(turn(1, big), rejection_turn(), turn(2, big), turn(3, big)), STATE,
                            context_window=8000)
    tools = {m['tool_call_id']: m['content'] for m in sent['messages'] if m['role'] == 'tool'}
    assert tools['f1'] == REJECTION                      # feedback kept verbatim
    assert tools['t1'].startswith('[平台已省略')          # evidence still stubbed (re-readable)
    assert report['estimate_after'] <= report['budget']


def test_state_carries_last_rejection_codes():
    state = dict(STATE, submission={'number': 2, 'accepted': False, 'error_codes': ['QUOTES_INVALID']})
    sent, _ = assemble(payload(turn(1, '验收后30天付款。')), state)
    assert '第2次，未通过（平台错误码：QUOTES_INVALID）' in sent['messages'][-1]['content']
    accepted = dict(STATE, submission={'number': 2, 'accepted': True, 'error_codes': []})
    assert '错误码' not in assemble(payload(turn(1, 'x')), accepted)[0]['messages'][-1]['content']


def test_runtime_passes_rejection_codes_into_trusted_state(client):
    ident = submit(client)
    def script(n, results):
        if n == 1:
            return reply(calls=[('read_clause', {'clause_id': 'clause-1'})])
        if n == 2:
            return reply(calls=[('submit_findings', findings('验收合格后300天内付款'))])
        return reply('完成')
    rt, detail, calls = run_script(client, ident, script)
    codes = next(e['data']['error_codes'] for e in rt.store.events(ident) if e['event_type'] == 'dsh.findings.checked')
    state = calls[2]['messages'][-1]['content']           # request after the rejection
    assert state.startswith('【平台状态，可信】')
    assert '第1次，未通过（平台错误码：' + '、'.join(codes) + '）' in state
