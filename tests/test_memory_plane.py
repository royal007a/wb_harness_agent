import json

import pytest
import yaml
from fastapi.testclient import TestClient

from backend.app import create_app
from backend.service import ROOT


SOURCE_A = {
    'source_ref': 'meeting:2026-09-18',
    'content': '张三最近明确说下午开会更合适。',
    'occurred_at': '2026-09-18T09:00:00Z',
    'data_classification': 'Internal',
}


@pytest.fixture
def client(tmp_path):
    with TestClient(create_app(tmp_path / 'memory.db', False), base_url='http://127.0.0.1') as value:
        yield value


def create_bank(client, name='project-memory', data_classification='Internal', key='bank-one'):
    response = client.post('/api/local/memory/banks', json={
        'name': name, 'scope': 'project', 'data_classification': data_classification, 'retention_days': 90,
    }, headers={'Idempotency-Key': key})
    assert response.status_code == 201, response.text
    return response.json()


def retain(client, bank_id, source=SOURCE_A, facts=None, key='retain-one'):
    body = {'source': source, 'facts': facts or [{
        'statement': '张三当前偏好下午开会。', 'kind': 'preference', 'confidence': 0.9,
        'occurred_at': '2026-09-18T09:00:00Z', 'valid_from': '2026-09-18T09:00:00Z', 'valid_to': None,
        'supersedes_fact_id': None,
    }]}
    response = client.post(f'/api/local/memory/banks/{bank_id}/retain', json=body, headers={'Idempotency-Key': key})
    assert response.status_code == 201, response.text
    return response.json(), body


def recall(client, bank_id, query, **extra):
    response = client.post(f'/api/local/memory/banks/{bank_id}:recall', json={'query': query, **extra})
    assert response.status_code == 200, response.text
    return response.json()


def test_m1_source_fact_evidence_bundle_is_provenanced_and_redacted(client):
    bank = create_bank(client)
    result, body = retain(client, bank['id'])
    assert result['deduplicated'] is False
    assert 'content' not in result['source']
    assert result['facts'][0]['source_id'] == result['source']['id']
    bundle = recall(client, bank['id'], '下午开会')
    assert bundle['schema_version'] == 'evidence-bundle@1'
    assert bundle['channels'] == ['keyword', 'temporal']
    assert bundle['memory_status'] == 'available'
    evidence = bundle['evidence'][0]
    assert evidence['statement'] == body['facts'][0]['statement']
    assert evidence['source_evidence']['source_id'] == result['source']['id']
    assert evidence['source_evidence']['content_sha256'] == result['source']['content_sha256']
    assert SOURCE_A['content'] not in json.dumps(bundle, ensure_ascii=False)
    detail = client.get('/api/local/memory/banks/' + bank['id']).json()
    assert detail['counts'] == {'sources': 1, 'facts': 1}


def test_bank_isolation_deduplication_and_restart_persistence(client, tmp_path):
    first = create_bank(client, 'alpha-memory', key='alpha-bank')
    second = create_bank(client, 'beta-memory', key='beta-bank')
    retained, body = retain(client, first['id'], key='alpha-retain')
    duplicate = client.post(f'/api/local/memory/banks/{first["id"]}/retain', json=body,
                            headers={'Idempotency-Key': 'alpha-retain-new-key'})
    assert duplicate.status_code == 201
    assert duplicate.json()['deduplicated'] is True
    assert recall(client, second['id'], '下午开会')['evidence'] == []
    assert client.post('/api/local/memory/banks', json={
        'name': 'alpha-memory', 'scope': 'project', 'data_classification': 'Internal', 'retention_days': 90,
    }, headers={'Idempotency-Key': 'duplicate-bank'}).status_code == 409
    assert retained['source']['bank_id'] != second['id']


def test_supersede_retract_and_delete_propagate_to_recall_and_storage(client):
    bank = create_bank(client)
    old, _ = retain(client, bank['id'], source={
        'source_ref': 'meeting:old', 'content': '张三此前说上午开会方便。',
        'occurred_at': '2026-08-01T09:00:00Z', 'data_classification': 'Internal',
    }, facts=[{
        'statement': '张三此前偏好上午开会。', 'kind': 'preference', 'confidence': 0.7,
        'occurred_at': '2026-08-01T09:00:00Z', 'valid_from': '2026-08-01T09:00:00Z', 'valid_to': None,
        'supersedes_fact_id': None,
    }], key='old')
    replacement, _ = retain(client, bank['id'], source=SOURCE_A, facts=[{
        'statement': '张三当前偏好下午开会。', 'kind': 'preference', 'confidence': 0.9,
        'occurred_at': '2026-09-18T09:00:00Z', 'valid_from': '2026-09-18T09:00:00Z', 'valid_to': None,
        'supersedes_fact_id': old['facts'][0]['id'],
    }], key='replacement')
    preferred = recall(client, bank['id'], '张三偏好开会')
    assert [item['id'] if 'id' in item else item['evidence_id'] for item in preferred['evidence']] == [replacement['facts'][0]['id']]
    retracted = client.post('/api/local/memory/sources/' + replacement['source']['id'] + ':retract', json={},
                            headers={'Idempotency-Key': 'retract-new'})
    assert retracted.status_code == 200 and retracted.json()['retracted_fact_count'] == 1
    assert recall(client, bank['id'], '张三偏好开会')['evidence'] == []
    deleted = client.delete('/api/local/memory/sources/' + old['source']['id'], headers={'Idempotency-Key': 'delete-old'})
    assert deleted.status_code == 200 and deleted.json()['status'] == 'deleted'
    with client.app.state.service.store.lock:
        row = client.app.state.service.store.db.execute('SELECT doc FROM memory_tombstones WHERE id=?',
                                                        (deleted.json()['tombstone_id'],)).fetchone()
        raw_source = client.app.state.service.store.db.execute('SELECT doc FROM memory_sources WHERE id=?',
                                                               (old['source']['id'],)).fetchone()
    assert raw_source is None
    assert '此前说上午' not in row['doc']
    assert old['source']['content_sha256'] in row['doc']


def test_sensitive_classification_unknown_field_and_cross_bank_supersede_rejected(client):
    public = create_bank(client, 'public-memory', 'Public', 'public-bank')
    internal_body = {'source': SOURCE_A, 'facts': [{
        'statement': '张三当前偏好下午开会。', 'kind': 'preference', 'confidence': 0.9,
        'occurred_at': '2026-09-18T09:00:00Z', 'valid_from': None, 'valid_to': None, 'supersedes_fact_id': None,
    }]}
    denied = client.post(f'/api/local/memory/banks/{public["id"]}/retain', json=internal_body,
                         headers={'Idempotency-Key': 'public-internal'})
    assert denied.status_code == 403 and denied.json()['error']['code'] == 'MEMORY_CLASSIFICATION_DENIED'
    sensitive = {**internal_body, 'source': {**SOURCE_A, 'content': 'access_token=abc'}}
    rejected = client.post(f'/api/local/memory/banks/{public["id"]}/retain', json=sensitive,
                           headers={'Idempotency-Key': 'sensitive-memory'})
    assert rejected.status_code == 422 and rejected.json()['error']['code'] == 'MEMORY_RETAIN_REJECTED'
    unknown = client.post('/api/local/memory/banks', json={
        'name': 'bad-bank', 'scope': 'project', 'data_classification': 'Internal', 'retention_days': 3, 'workspace_id': 'other',
    }, headers={'Idempotency-Key': 'unknown-bank'})
    assert unknown.status_code == 422

    alpha = create_bank(client, 'supersede-alpha', key='supersede-alpha-bank')
    beta = create_bank(client, 'supersede-beta', key='supersede-beta-bank')
    beta_result, _ = retain(client, beta['id'], key='beta-fact')
    cross_body = {
        'source': {**SOURCE_A, 'source_ref': 'meeting:cross', 'content': '另一条确认记录。'},
        'facts': [{
            'statement': '不同 Bank 不能纠正其他 Bank 的事实。', 'kind': 'fact', 'confidence': 1,
            'occurred_at': '2026-09-18T10:00:00Z', 'valid_from': None, 'valid_to': None,
            'supersedes_fact_id': beta_result['facts'][0]['id'],
        }],
    }
    cross = client.post(f'/api/local/memory/banks/{alpha["id"]}/retain', json=cross_body,
                        headers={'Idempotency-Key': 'cross-bank-supersede'})
    assert cross.status_code == 404 and cross.json()['error']['code'] == 'MEMORY_FACT_NOT_FOUND'
    assert client.get('/api/local/memory/banks/' + alpha['id']).json()['counts'] == {'sources': 0, 'facts': 0}


def test_retention_filters_expired_evidence_and_state_survives_restart(tmp_path):
    database = tmp_path / 'restart-memory.db'
    with TestClient(create_app(database, False), base_url='http://127.0.0.1') as local:
        bank = create_bank(local, 'restart-memory', 'Public', 'restart-bank')
        source = {**SOURCE_A, 'data_classification': 'Public', 'source_ref': 'note:public', 'content': '公开的下午会议约定。'}
        retained, _ = retain(local, bank['id'], source=source, facts=[{
            'statement': '公开约定在下午会议。', 'kind': 'decision', 'confidence': 1,
            'occurred_at': '2026-09-18T09:00:00Z', 'valid_from': None, 'valid_to': None, 'supersedes_fact_id': None,
        }], key='restart-retain')
        assert retained['source']['status'] == 'active'
        assert recall(local, bank['id'], '下午会议')['memory_status'] == 'available'
        expired = recall(local, bank['id'], '下午会议', as_of='2037-01-01T00:00:00Z')
        assert expired == {**expired, 'memory_status': 'empty', 'evidence': []}
    with TestClient(create_app(database, False), base_url='http://127.0.0.1') as restarted:
        assert recall(restarted, bank['id'], '下午会议')['memory_status'] == 'available'


def test_memory_openapi_declares_the_same_local_contract(client):
    static = yaml.safe_load((ROOT / 'specs/v1/openapi.yaml').read_text())
    paths = client.app.openapi()['paths']
    pairs = {
        '/local/memory/runtime': '/api/local/memory/runtime',
        '/local/memory/banks': '/api/local/memory/banks',
        '/local/memory/banks/{bankId}/retain': '/api/local/memory/banks/{bank_id}/retain',
        '/local/memory/banks/{bankId}:recall': '/api/local/memory/banks/{bank_id}:recall',
        '/local/memory/sources/{sourceId}:retract': '/api/local/memory/sources/{source_id}:retract',
        '/local/memory/sources/{sourceId}': '/api/local/memory/sources/{source_id}',
    }
    for static_path, runtime_path in pairs.items():
        assert static_path in static['paths']
        assert runtime_path in paths
    assert paths['/api/local/memory/banks/{bank_id}:recall']['post']['responses']['200']['content']['application/json']['schema'] == {
        '$ref': '#/components/schemas/evidence_bundle'}
    assert paths['/api/local/memory/banks/{bank_id}/retain']['post']['requestBody']['content']['application/json']['schema'] == {
        '$ref': '#/components/schemas/retain_request'}
