"""HA-0111: single-party claims whose values belong to another party in the quote are flagged."""
import json

import pytest

from backend.dsh_findings import unbound_party_values
from test_dsh_payment_findings import client, submit, reply, run_script, findings, slot, q, artifact  # noqa: F401


def Q(text):
    return [{'clause_id': 'clause-1', 'text': text}]


@pytest.mark.parametrize('claim,quote,expected', [
    ('乙方应在30日内支付', '甲方30日内支付，乙方60日内开票', True),        # swapped roles (jikesummary 提示链: 总额对、逐行对调)
    ('乙方应在30天内开具发票', '甲方应在验收合格后30天内付款', True),
    ('乙方应在30日内支付', '乙方提交发票后，甲方30日内支付', True),         # nearest party, not any earlier one
    ('甲方应在30日内支付', '甲方30日内支付，乙方60日内开票', False),
    ('甲方应在验收合格后30天内付款', '甲方应在验收合格后，于30天内向乙方支付合同款', False),  # comma split is fine
    ('验收合格后30天内付款', '甲方30日内支付', False),                    # no party in claim: not checked
    ('甲方和乙方30日内对账', '甲方30日内付款，乙方30日内开票', False),       # two parties: not checked
    ('乙方收款期限30天', '付款期限30天', False),                           # no party in quote: undecidable
])
def test_binding_rule(claim, quote, expected):
    assert unbound_party_values(claim, Q(quote)) is expected


DOC = '第1条 付款与开票\n甲方应在验收合格后30日内支付合同款，乙方应在60日内开具发票。'


def run_doc(client, claim, quote):
    ident = submit(client, document=DOC)
    def script(n, results):
        if n == 1:
            return reply(calls=[('read_clause', {'clause_id': 'clause-1'})])
        if n == 2:
            f = findings()
            f['term'] = slot('supported', claim, [q('clause-1', quote)])
            f['trigger'] = slot('supported', '验收合格', [q('clause-1', '验收合格')])
            return reply(calls=[('submit_findings', f)])
        return reply('完成')
    rt, detail, _ = run_script(client, ident, script)
    return rt, detail


def test_swapped_party_is_published_only_with_flag(client):
    rt, detail = run_doc(client, '乙方应在30日内支付合同款', '甲方应在验收合格后30日内支付合同款，乙方应在60日内开具发票')
    assert detail['run']['status'] == 'succeeded'
    record = json.loads(artifact(rt, detail, 'dsh-findings.json'))
    assert any(g['code'] == 'CLAIM_PARTY_VALUE_UNBOUND' for g in record['platform_gaps'])
    assert record['business_status'] == 'partial' and '主体与数值' in artifact(rt, detail, 'dsh-analysis.txt')


def test_correct_party_is_not_flagged(client):
    rt, detail = run_doc(client, '甲方应在验收合格后30日内支付合同款', '甲方应在验收合格后30日内支付合同款')
    record = json.loads(artifact(rt, detail, 'dsh-findings.json'))
    assert not any(g['code'] == 'CLAIM_PARTY_VALUE_UNBOUND' for g in record['platform_gaps'])
