"""HA-0093: structural boundaries, not legal numbering or semantic evidence."""
import hashlib

import pytest

from backend.adaptive_retrieval import build_parent_child_chunks, validate_adaptive_chunks

NUMBERS = ('一', '二', '三', '四', '五', '六', '七', '八', '九', '十', '十一', '十二')


def document(chinese=True, newline='\n', indent=''):
    return newline.join(f'{indent}第{n if chinese else i}条 条款{i}{newline}{indent}唯一标记{i}：甲方付款。'
                        for i, n in enumerate(NUMBERS, 1))


def assert_slices(result):
    validate_adaptive_chunks(result)
    for part in result['parents'] + result['children']:
        assert result['source_text'][part['start']:part['end']] == part['text']
        assert part['text_sha256'] == hashlib.sha256(part['text'].encode()).hexdigest()


@pytest.mark.parametrize('newline', ['\n', '\r\n', '\r'])
@pytest.mark.parametrize('indent', ['', '  ', '\t'])
def test_twelve_chinese_clauses_keep_separate_full_slices(newline, indent):
    result = build_parent_child_chunks(document(newline=newline, indent=indent))
    assert len(result['parents']) == len(result['children']) == 12
    for i, child in enumerate(result['children'], 1):
        assert f'唯一标记{i}：' in child['text']
        assert child['heading'] == f'条款{i}'
        assert child['text'].count('唯一标记') == 1
    assert_slices(result)


@pytest.mark.parametrize('number', ['十', '十一', '二十', '一百零一', '一百〇二', '两百', '一千', '一万'])
def test_chinese_number_characters_define_boundaries(number):
    result = build_parent_child_chunks(f'第一条 前条\n正文。\n第{number}条 后条\n另文。')
    assert [p['heading'] for p in result['parents']] == ['前条', '后条']
    assert_slices(result)


def test_arabic_heading_output_is_unchanged():
    result = build_parent_child_chunks(document(chinese=False))
    assert len(result['parents']) == len(result['children']) == 12
    assert [p['heading'] for p in result['parents']] == [f'条款{i}' for i in range(1, 13)]
    assert_slices(result)


def test_inline_cross_reference_is_not_a_heading():
    result = build_parent_child_chunks('第一条 内容\n应依照第十二条办理。\n第二条 其他\n没有新增标题。')
    assert len(result['parents']) == 2
    assert '应依照第十二条办理。' in result['children'][0]['text']
    assert_slices(result)


def test_long_chinese_clauses_are_bounded_and_not_one_clause_one_chunk():
    text = '第一条 长条款\n' + '原始内容。' * 1300 + '\n第二条 最后条\n最后唯一标记。'
    result = build_parent_child_chunks(text, max_child_chars=400, parent_max_chars=1000)
    assert len(result['children']) > 2
    assert all(p['char_count'] <= 1000 for p in result['parents'])
    assert all(c['char_count'] <= 400 for c in result['children'])
    assert result['children'][-1]['text'] == '第二条 最后条\n最后唯一标记。'
    assert_slices(result)


def test_actual_sdk_can_read_twelfth_chinese_clause(tmp_path, monkeypatch):
    import json
    from fastapi.testclient import TestClient
    from backend.app import create_app
    from backend.agent_runtime import KeyringCredentialResolver
    from backend.dsh_provider import parse_response

    monkeypatch.setenv('HARNESS_DSH_LOCAL', 'enabled')
    monkeypatch.setenv('HARNESS_DSH_RUN_ROOT', str(tmp_path.resolve() / 'owned'))
    monkeypatch.delenv('HARNESS_DSH_REAL_ENABLED', raising=False)
    monkeypatch.setattr(KeyringCredentialResolver, 'resolve', lambda *a: pytest.fail('no credentials'))
    calls, observations = [], []

    async def provider(payload, limit):
        calls.append(payload)
        results = [json.loads(m['content']) for m in payload['messages'] if m['role'] == 'tool']
        if len(calls) == 1:
            name, args = 'read_clause', {'clause_id': 'clause-12'}
        else:
            observations.append(results[-1])
            return parse_response({'choices': [{'finish_reason': 'stop', 'message': {'content': '合成测试结果，引用 clause-12。'}}],
                'usage': {'prompt_tokens': 10, 'completion_tokens': 10, 'total_tokens': 20}})
        return parse_response({'choices': [{'finish_reason': 'tool_calls', 'message': {'content': '',
            'tool_calls': [{'id': 'same_across_turns', 'type': 'function', 'function': {
                'name': name, 'arguments': json.dumps(args, ensure_ascii=False)}}]}}],
            'usage': {'prompt_tokens': 10, 'completion_tokens': 10, 'total_tokens': 20}})

    with TestClient(create_app(tmp_path / 'test.db', run_worker=False), base_url='http://localhost') as client:
        response = client.post('/api/local/dsh/runs', json={
            'objective': '核对最后一条', 'document': document(), 'mode': 'integration_probe',
            'public_data_confirmed': True, 'timeout_seconds': 300}, headers={'Idempotency-Key': 'cn12'})
        assert response.status_code == 201, response.text
        ident = response.json()['initial_run']['id']
        rt = client.app.state.service.dsh
        rt.send_probe = provider
        rt.execute(ident)
        detail = rt.detail(ident)
        assert detail['run']['status'] == 'succeeded', (detail['run']['exit_reason'], len(calls))
        assert len(calls) == detail['budget']['calls'] == 2
        # free retains its original list-shaped tool response protocol.
        assert observations == [[{'clause_id': 'clause-12', 'text': '第十二条 条款12\n唯一标记12：甲方付款。'}]]
        assert detail['budget']['reserved'] == 0
        events = rt.store.events(ident)
        assert sum(e['event_type'] == 'dsh.tool.completed' for e in events) == 1
        assert '唯一标记' not in json.dumps(events, ensure_ascii=False)
        assert not list((tmp_path.resolve() / 'owned').glob('run-*'))
