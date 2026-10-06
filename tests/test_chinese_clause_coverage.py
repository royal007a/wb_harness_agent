"""HA-0090: structural splitting must not silently remove exception warnings."""
import json

import pytest

from backend.adaptive_retrieval import build_parent_child_chunks
from backend.dsh_findings import candidates, verify
from test_dsh_payment_findings import client, submit, run_script, reply, findings, slot, q, artifact  # noqa: F401


@pytest.mark.parametrize('numbers', [('一', '二'), ('1', '2')])
def test_separate_exception_without_payment_word_stays_a_candidate(numbers):
    text = f'第{numbers[0]}条 付款\n甲方应在验收合格后30天内向乙方支付合同款。\n第{numbers[1]}条 特殊安排\n发生质量争议时，期限延期。'
    chunks = build_parent_child_chunks(text)
    clauses = {f'clause-{i+1}': c['text'] for i, c in enumerate(chunks['children'])}
    assert len(clauses) == 2
    assert candidates(clauses) == {'payment': ['clause-1'], 'exception': ['clause-2']}
    result = verify(findings(), clauses, {'clause-1'})
    assert result['errors'] == []
    assert result['platform_gaps'] == [{'code': 'EXCEPTION_CANDIDATES_UNREAD', 'clause_ids': ['clause-2']}]
    read = verify(findings(), clauses, {'clause-1', 'clause-2'})
    assert read['platform_gaps'] == [{'code': 'EXCEPTION_CANDIDATE_NOT_REPORTED', 'clause_ids': ['clause-2']}]


@pytest.mark.parametrize('clauses,expected', [
    ({'clause-1': '质量争议时延期。'}, {'payment': [], 'exception': []}),
    ({'clause-1': '30天付款。', 'clause-2': '双方签字。'}, {'payment': ['clause-1'], 'exception': []}),
    # Conservative false positive explicitly retained, not called semantic relevance.
    ({'clause-1': '30天付款。', 'clause-2': '设备维护争议另行处理。'}, {'payment': ['clause-1'], 'exception': ['clause-2']}),
])
def test_candidate_policy_boundaries(clauses, expected):
    assert candidates(clauses) == expected


def test_sdk_requires_cross_clause_gap_before_accepted_publication(client):
    text = '第一条 付款\n甲方应在验收合格后30天内向乙方支付合同款。\n第二条 特殊安排\n发生质量争议时，期限延期。'
    ident = submit(client, document=text)
    observed = []
    def script(n, results):
        if n == 1:
            return reply(calls=[('read_clause', {'clause_id': 'clause-1'})])
        if n == 2:
            return reply(calls=[('submit_findings', findings())])
        if n == 3:
            observed.append(results[-1])
            return reply(calls=[('read_clause', {'clause_id': 'clause-2'})])
        if n == 4:
            return reply(calls=[('submit_findings', findings(exception=slot('supported',
                '发生质量争议时，期限延期', [q('clause-2', '发生质量争议时，期限延期')])) )])
        return reply('合成核对结束，clause-1、clause-2。')
    rt, detail, calls = run_script(client, ident, script)
    assert detail['run']['status'] == 'succeeded', detail['run']['exit_reason']
    assert observed[0].get('accepted') is False
    assert observed[0]['coverage_gap'] == {'code': 'EXCEPTION_CANDIDATES_UNREAD', 'clause_ids': ['clause-2']}
    record = json.loads(artifact(rt, detail, 'dsh-findings.json'))
    assert record['candidates']['exception'] == ['clause-2']
    assert record['platform_gaps'] == []
    assert record['findings']['exception']['quotes'][0]['clause_id'] == 'clause-2'
    assert len(calls) == detail['budget']['calls'] == 5
