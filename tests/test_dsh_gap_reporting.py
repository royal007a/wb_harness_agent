"""HA-0115: both unread gaps are reported (jikesummary 扇出聚合: 盘点缺席要如实)."""
from backend.dsh_findings import verify

CLAUSES = {'clause-1': '甲方应在验收合格后30天内向乙方支付合同款。', 'clause-2': '付款前乙方开具发票。',
           'clause-3': '发生质量争议时，甲方可暂停付款。'}


def submission():
    slot = lambda s='unknown', c='', q=(): {'status': s, 'claim': c, 'quotes': list(q)}
    return {'term': slot('supported', '验收合格后30天内付款', [{'clause_id': 'clause-1', 'text': '验收合格后30天内向乙方支付合同款'}]),
            'trigger': slot(), 'exception': slot(), 'conflict': slot()}


def codes(result):
    return {g['code']: g['clause_ids'] for g in result['platform_gaps']}


def test_both_gaps_reported_without_duplicates():
    result = verify(submission(), CLAUSES, {'clause-1'})
    assert codes(result) == {'EXCEPTION_CANDIDATES_UNREAD': ['clause-3'], 'PAYMENT_CLAUSES_UNREAD': ['clause-2']}


def test_only_payment_gap_when_exceptions_read():
    result = verify(submission(), CLAUSES, {'clause-1', 'clause-3'})
    assert codes(result).get('PAYMENT_CLAUSES_UNREAD') == ['clause-2']
    assert 'EXCEPTION_CANDIDATES_UNREAD' not in codes(result)
