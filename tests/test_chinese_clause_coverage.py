"""HA-0090: real structural context, not whole-document co-occurrence."""
import json

import pytest

from backend.adaptive_retrieval import build_parent_child_chunks
from backend.dsh_findings import candidates, verify
from test_dsh_payment_findings import client, submit, run_script, reply, findings, slot, q, artifact  # noqa: F401


def split(text, **limits):
    chunks = build_parent_child_chunks(text, **limits)['children']
    clauses = {f'clause-{i+1}': c['text'] for i, c in enumerate(chunks)}
    context = {f'clause-{i+1}': {'parent_id': c['parent_id'], 'structural_path': c['structural_path']}
               for i, c in enumerate(chunks)}
    return clauses, context


@pytest.mark.parametrize('heading,parent_limit', [('事项', 3000), ('付款', 1000)])
@pytest.mark.parametrize('numbers', [('一', '二'), ('1', '2')])
def test_split_exception_uses_parent_or_payment_path(heading, parent_limit, numbers):
    text = (f'第{numbers[0]}条 {heading}\n甲方应在验收合格后30天内向乙方支付合同款。\n'
            + '背景说明。' * 220 + '\n发生质量争议时，期限延期。\n'
            + f'第{numbers[1]}条 争议解决\n争议提交法院处理。')
    clauses, context = split(text, max_child_chars=400, parent_max_chars=parent_limit)
    target = next(k for k, v in clauses.items() if '期限延期' in v)
    last = list(clauses)[-1]
    assert target != 'clause-1' and last != target
    if heading == '事项':
        assert context[target]['parent_id'] == context['clause-1']['parent_id']
    else:
        assert context[target]['parent_id'] != context['clause-1']['parent_id']
    assert candidates(clauses, context)['exception'] == [target]
    result = verify(findings(), clauses, {'clause-1'}, chunk_context=context)
    assert result['errors'] == []
    assert result['platform_gaps'] == [{'code': 'EXCEPTION_CANDIDATES_UNREAD', 'clause_ids': [target]}]
    read = verify(findings(), clauses, set(clauses), chunk_context=context)
    assert read['platform_gaps'] == [{'code': 'EXCEPTION_CANDIDATE_NOT_REPORTED', 'clause_ids': [target]}]


@pytest.mark.parametrize('text', [
    '第一条 付款\n30天付款。\n第二条 争议解决\n争议提交法院处理。',
    '第一条 付款\n30天付款。\n第二条 独立事项\n设备维护争议另行处理。',
    # Independent implicit relation is not claimed to be understood.
    '第一条 付款\n30天付款。\n第二条 特殊安排\n发生质量争议时，期限延期。',
])
def test_independent_sibling_does_not_inherit_payment_scope(text):
    clauses, context = split(text)
    assert candidates(clauses, context) == {'payment': ['clause-1'], 'exception': []}


def test_missing_context_no_payment_and_no_exception_boundaries():
    assert candidates({'a': '30天付款。', 'b': '争议延期。'})['exception'] == []
    assert candidates({'a': '质量争议时延期。'}) == {'payment': [], 'exception': []}
    assert candidates({'a': '30天付款。', 'b': '双方签字。'})['exception'] == []


def test_sdk_requires_structural_gap_before_accepted_publication(client):
    text = ('第一条 付款\n甲方应在验收合格后30天内向乙方支付合同款。\n'
            + '背景说明。' * 350 + '\n发生质量争议时，期限延期。\n'
            + '第二条 争议解决\n争议提交法院处理。')
    clauses, _ = split(text, max_child_chars=1500, parent_max_chars=3000)
    assert len(clauses) == 3 and '期限延期' in clauses['clause-2']
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
    assert detail['plan']['candidates']['exception'] == ['clause-2']
