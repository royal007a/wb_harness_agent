import json

from fastapi.testclient import TestClient

from backend.app import create_app


def request(client, method, path, body=None, key=None):
    response = client.request(method, path, json=body, headers={'Idempotency-Key': key} if key else {})
    assert response.status_code in {200, 201}, response.text
    return response.json()


def test_fact_lineage_is_bounded_provenanced_and_current_is_not_overwritten(tmp_path):
    with TestClient(create_app(tmp_path / 'lineage.db', False), base_url='http://127.0.0.1') as client:
        bank = request(client, 'POST', '/api/local/memory/banks', {'name': 'lineage', 'scope': 'project', 'data_classification': 'Internal', 'retention_days': 90}, 'bank')
        old = request(client, 'POST', f'/api/local/memory/banks/{bank["id"]}/retain', {
            'source': {'source_ref': 'old:meeting', 'content': '旧来源正文不得回显。', 'occurred_at': '2026-09-01T09:00:00Z', 'data_classification': 'Internal'},
            'facts': [{'statement': '张三偏好上午开会。', 'kind': 'preference', 'confidence': .7, 'occurred_at': '2026-09-01T09:00:00Z', 'valid_from': '2026-09-01T09:00:00Z', 'valid_to': None, 'supersedes_fact_id': None}],
        }, 'old')
        current = request(client, 'POST', f'/api/local/memory/banks/{bank["id"]}/retain', {
            'source': {'source_ref': 'new:meeting', 'content': '新来源正文不得回显。', 'occurred_at': '2026-09-20T09:00:00Z', 'data_classification': 'Internal'},
            'facts': [{'statement': '张三偏好下午开会。', 'kind': 'preference', 'confidence': .9, 'occurred_at': '2026-09-20T09:00:00Z', 'valid_from': '2026-09-20T09:00:00Z', 'valid_to': None, 'supersedes_fact_id': old['facts'][0]['id']}],
        }, 'new')
        endpoint = f'/api/local/memory/banks/{bank["id"]}:fact-lineage'
        lineage = request(client, 'POST', endpoint, {'fact_id': current['facts'][0]['id']})
        assert lineage['lineage_status'] == 'available'
        assert [item['statement'] for item in lineage['facts']] == ['张三偏好下午开会。', '张三偏好上午开会。']
        assert [item['applicability'] for item in lineage['facts']] == ['current_applicable', 'historical']
        assert all('来源正文' not in json.dumps(item, ensure_ascii=False) for item in lineage['facts'])
        before = request(client, 'POST', endpoint, {'fact_id': current['facts'][0]['id'], 'as_of': '2026-09-10T00:00:00Z'})
        assert before['lineage_status'] == 'empty'
        other = request(client, 'POST', '/api/local/memory/banks', {'name': 'other', 'scope': 'project', 'data_classification': 'Internal', 'retention_days': 90}, 'other')
        cross = request(client, 'POST', f'/api/local/memory/banks/{other["id"]}:fact-lineage', {'fact_id': current['facts'][0]['id']})
        assert cross['lineage_status'] == 'empty' and cross['facts'] == []
