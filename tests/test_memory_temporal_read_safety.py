import json

import pytest
from fastapi.testclient import TestClient

from backend.app import create_app


@pytest.fixture
def client(tmp_path):
    with TestClient(create_app(tmp_path / 'memory-temporal-read-safety.db', False), base_url='http://127.0.0.1') as value:
        yield value


def request(client, method, path, *, body=None, key=None, status=(200, 201)):
    response = client.request(method, path, json=body, headers={'Idempotency-Key': key} if key else {})
    assert response.status_code in status, response.text
    return response.json()


def bank(client, name, key):
    return request(client, 'POST', '/api/local/memory/banks', key=key, body={
        'name': name, 'scope': 'project', 'data_classification': 'Internal', 'retention_days': 90,
    })


def retain(client, bank_id, ref, source_time, facts, key, *, content='未来来源正文不应在任何读取路径回显。'):
    return request(client, 'POST', f'/api/local/memory/banks/{bank_id}/retain', key=key, body={
        'source': {'source_ref': ref, 'content': content, 'occurred_at': source_time, 'data_classification': 'Internal'},
        'facts': [{
            'statement': statement, 'kind': kind, 'confidence': 0.9, 'detail': detail,
            'occurred_at': occurred_at, 'valid_from': valid_from, 'valid_to': valid_to,
            'supersedes_fact_id': None,
        } for statement, kind, detail, occurred_at, valid_from, valid_to in facts],
    })


def recall(client, bank_id, query, as_of):
    return request(client, 'POST', f'/api/local/memory/banks/{bank_id}:recall', body={'query': query, 'as_of': as_of})


def context(client, bank_id, query, as_of):
    return request(client, 'POST', f'/api/local/memory/banks/{bank_id}:context', body={'query': query, 'as_of': as_of})


def details(client, bank_id, ids, as_of):
    return request(client, 'POST', f'/api/local/memory/banks/{bank_id}:recall-details', body={'evidence_ids': ids, 'as_of': as_of})


def test_future_source_is_hidden_consistently_until_its_as_of_time(client):
    target = bank(client, 'future-source', 'future-source-bank')
    stored = retain(client, target['id'], 'future:source', '2026-09-22T10:00:00Z', [
        ('未来发布计划已确认。', 'decision', '未来发布的受限详情。', '2026-09-22T10:00:00Z', '2026-09-22T10:00:00Z', None),
    ], 'future-source-retain')
    fact_id = stored['facts'][0]['id']
    before = '2026-09-21T23:59:59Z'
    assert recall(client, target['id'], '未来发布', before)['memory_status'] == 'empty'
    assert context(client, target['id'], '未来发布', before)['context_status'] == 'empty'
    hidden = details(client, target['id'], [fact_id], before)
    assert hidden['memory_status'] == 'empty' and hidden['unavailable_evidence_ids'] == [fact_id]
    after = '2026-09-22T10:00:00Z'
    assert recall(client, target['id'], '未来发布', after)['evidence'][0]['evidence_id'] == fact_id
    capsule = context(client, target['id'], '未来发布', after)
    assert capsule['detail_catalog'][0]['evidence_id'] == fact_id
    visible = details(client, target['id'], [fact_id], after)
    assert visible['details'][0]['detail'] == '未来发布的受限详情。'
    assert '未来来源正文' not in json.dumps(visible, ensure_ascii=False)


def test_future_fact_on_current_source_is_hidden_without_bypassing_fts(client):
    target = bank(client, 'future-fact', 'future-fact-bank')
    stored = retain(client, target['id'], 'current:source', '2026-09-20T10:00:00Z', [
        ('当前事实可见。', 'fact', '当前详情。', '2026-09-20T10:00:00Z', '2026-09-20T10:00:00Z', None),
        ('未来风险评审结果。', 'state', '未来详情。', '2026-09-23T10:00:00Z', '2026-09-23T10:00:00Z', None),
    ], 'future-fact-retain')
    present_id, future_id = (item['id'] for item in stored['facts'])
    before = '2026-09-21T10:00:00Z'
    current = recall(client, target['id'], '当前事实', before)
    assert [item['evidence_id'] for item in current['evidence']] == [present_id]
    assert recall(client, target['id'], '未来风险', before)['memory_status'] == 'empty'
    assert context(client, target['id'], '未来风险', before)['context_status'] == 'empty'
    assert details(client, target['id'], [future_id], before)['unavailable_evidence_ids'] == [future_id]
    after = '2026-09-23T10:00:00Z'
    assert recall(client, target['id'], '未来风险', after)['evidence'][0]['evidence_id'] == future_id


def test_temporal_read_filter_persists_after_restart(tmp_path):
    database = tmp_path / 'temporal-restart.db'
    with TestClient(create_app(database, False), base_url='http://127.0.0.1') as local:
        target = bank(local, 'restart-temporal', 'restart-temporal-bank')
        stored = retain(local, target['id'], 'restart:future', '2026-09-25T10:00:00Z', [
            ('未来排期已登记。', 'state', '未来排期详情。', '2026-09-25T10:00:00Z', '2026-09-25T10:00:00Z', None),
        ], 'restart-temporal-retain')
        fact_id = stored['facts'][0]['id']
        assert details(local, target['id'], [fact_id], '2026-09-24T10:00:00Z')['memory_status'] == 'empty'
    with TestClient(create_app(database, False), base_url='http://127.0.0.1') as restarted:
        assert restarted.get('/api/local/memory/runtime').json()['as_of_visibility'] == {
            'source_occurred_at': True, 'fact_occurred_at': True, 'fact_validity_window': True,
        }
        assert recall(restarted, target['id'], '未来排期', '2026-09-24T10:00:00Z')['memory_status'] == 'empty'
        assert details(restarted, target['id'], [fact_id], '2026-09-25T10:00:00Z')['memory_status'] == 'available'
