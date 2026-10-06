"""HA-0110: literal search ignores whitespace, case and full/half width (jikesummary 容错艺术)."""
import pytest

from backend.dsh_runtime import search_key
from test_dsh_payment_findings import client, submit, reply, run_script, tool_results  # noqa: F401

DOC = '第1条 付款\n甲方应在验收合格后３０天内付 款。\n第2条 交付\n乙方按 ＳＯＷ 交付。'


@pytest.mark.parametrize('query,clause', [('30天', 'clause-1'), ('付款', 'clause-1'), ('sow', 'clause-2'),
                                          ('付 款', 'clause-1'), ('SOW', 'clause-2')])
def test_search_tolerates_width_case_and_spaces(client, query, clause):
    ident = submit(client, template='free', document=DOC)
    rt, detail, calls = run_script(client, ident, lambda n, r: reply(calls=[('search_document', {'query': query})])
                                   if n == 1 else reply(f'见 {clause}'))
    result = tool_results(calls[1])[0]
    ids = [m['clause_id'] for m in (result['matches'] if isinstance(result, dict) else result)]
    assert clause in ids, (query, result)


def test_whitespace_only_query_is_rejected_not_match_all(client):
    ident = submit(client, template='free', document=DOC)
    rt, detail, _ = run_script(client, ident, lambda n, r: reply(calls=[('search_document', {'query': '　 '})])
                               if n == 1 else reply('见 clause-1'))
    assert detail['run']['exit_reason'] == 'DSH_TOOL_INPUT'


def test_returned_text_is_original_not_normalized(client):
    ident = submit(client, template='free', document=DOC)
    rt, detail, calls = run_script(client, ident, lambda n, r: reply(calls=[('search_document', {'query': '30天'})])
                                   if n == 1 else reply('见 clause-1'))
    result = tool_results(calls[1])[0]
    texts = [m['text'] for m in (result['matches'] if isinstance(result, dict) else result)]
    assert any('３０天内付 款' in t for t in texts)          # evidence stays verbatim for literal quote checks


def test_search_key():
    assert search_key('付 款 Ｓ１　ＡＢＣ') == '付款s1abc' and search_key(' 　\n') == ''
