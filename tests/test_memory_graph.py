import json

import pytest
import yaml
from fastapi.testclient import TestClient

from backend.app import create_app
from backend.service import ROOT


@pytest.fixture
def client(tmp_path):
    with TestClient(create_app(tmp_path / 'memory-graph.db', False), base_url='http://127.0.0.1') as value:
        yield value


def bank(client, name, key):
    response = client.post('/api/local/memory/banks', json={
        'name': name, 'scope': 'project', 'data_classification': 'Internal', 'retention_days': 90,
    }, headers={'Idempotency-Key': key})
    assert response.status_code == 201, response.text
    return response.json()


def retain(client, bank_id, ref, facts, key, content='原始来源正文，绝不能被 Graph Bundle 回显。'):
    response = client.post(f'/api/local/memory/banks/{bank_id}/retain', json={
        'source': {'source_ref': ref, 'content': content, 'occurred_at': '2026-09-20T09:00:00Z',
                   'data_classification': 'Internal'},
        'facts': facts,
    }, headers={'Idempotency-Key': key})
    assert response.status_code == 201, response.text
    return response.json()


def fact(statement, occurred_at='2026-09-20T09:00:00Z', valid_to=None):
    return {'statement': statement, 'kind': 'fact', 'confidence': 0.9, 'occurred_at': occurred_at,
            'valid_from': occurred_at, 'valid_to': valid_to, 'supersedes_fact_id': None}


def entity(client, bank_id, name, entity_type, support_fact_id, key, **extra):
    response = client.post(f'/api/local/memory/banks/{bank_id}/entities', json={
        'canonical_name': name, 'entity_type': entity_type, 'aliases': extra.pop('aliases', []),
        'support_fact_id': support_fact_id, 'valid_from': extra.pop('valid_from', None),
        'valid_to': extra.pop('valid_to', None), **extra,
    }, headers={'Idempotency-Key': key})
    assert response.status_code == 201, response.text
    return response.json()


def relation(client, bank_id, subject_id, predicate, object_id, support_fact_id, key, **extra):
    response = client.post(f'/api/local/memory/banks/{bank_id}/relations', json={
        'subject_entity_id': subject_id, 'predicate': predicate, 'object_entity_id': object_id,
        'support_fact_id': support_fact_id, 'confidence': 0.9, 'occurred_at': '2026-09-20T09:00:00Z',
        'valid_from': '2026-09-20T09:00:00Z', 'valid_to': None, **extra,
    }, headers={'Idempotency-Key': key})
    assert response.status_code == 201, response.text
    return response.json()


def graph(client, bank_id, start_entity_id, **extra):
    response = client.post(f'/api/local/memory/banks/{bank_id}:graph-recall', json={
        'start_entity_id': start_entity_id, **extra,
    })
    assert response.status_code == 200, response.text
    return response.json()


def dependency_fixture(client, name='dependency-graph'):
    target = bank(client, name, name + '-bank')
    retained = retain(client, target['id'], 'systems:dependency', [
        fact('小李负责支付系统。'),
        fact('支付系统依赖风控服务。'),
        fact('风控服务在 2026-09-20 发生故障。'),
    ], name + '-retain')
    facts = retained['facts']
    person = entity(client, target['id'], '小李', 'person', facts[0]['id'], name + '-person')
    payment = entity(client, target['id'], '支付系统', 'system', facts[0]['id'], name + '-payment', aliases=['支付'])
    risk = entity(client, target['id'], '风控服务', 'system', facts[1]['id'], name + '-risk')
    first = relation(client, target['id'], person['entity']['id'], 'responsible_for', payment['entity']['id'],
                     facts[0]['id'], name + '-responsible')
    second = relation(client, target['id'], payment['entity']['id'], 'depends_on', risk['entity']['id'],
                      facts[1]['id'], name + '-depends')
    return target, retained, (person, payment, risk), (first, second)


def test_explicit_two_hop_graph_path_is_provenanced_and_redacted(client):
    target, retained, entities, _ = dependency_fixture(client)
    bundle = graph(client, target['id'], entities[0]['entity']['id'], max_hops=2, limit=10)
    assert bundle['schema_version'] == 'graph-evidence-bundle@1'
    assert bundle['channels'] == ['graph', 'temporal']
    assert bundle['memory_status'] == 'available'
    two_hop = next(path for path in bundle['paths'] if path['hop_count'] == 2)
    assert [node['canonical_name'] for node in two_hop['nodes']] == ['小李', '支付系统', '风控服务']
    assert [edge['predicate'] for edge in two_hop['edges']] == ['responsible_for', 'depends_on']
    assert two_hop['edges'][1]['support_evidence']['evidence_id'] == retained['facts'][1]['id']
    assert two_hop['edges'][1]['support_evidence']['source_ref'] == 'systems:dependency'
    assert '原始来源正文' not in json.dumps(bundle, ensure_ascii=False)
    assert bundle['safety'] == {
        'raw_source_content_included': False, 'model_calls': 0, 'automatic_entity_resolution': False,
    }
    runtime = client.get('/api/local/memory/runtime').json()
    assert runtime['mode'] == 'memory-plane-m3b@1'
    assert runtime['graph_recall'] == {
        'engine': 'sqlite-explicit-relation-store@1', 'max_hops': 2, 'automatic_entity_resolution': False,
    }


def test_graph_requires_active_same_bank_support_and_rejects_self_loop(client):
    alpha, retained, entities, _ = dependency_fixture(client, 'alpha-graph')
    beta = bank(client, 'beta-graph', 'beta-graph-bank')
    cross_fact = entity(client, alpha['id'], '支付平台', 'system', retained['facts'][0]['id'], 'alpha-extra')
    cross = client.post(f'/api/local/memory/banks/{beta["id"]}/entities', json={
        'canonical_name': '越权实体', 'entity_type': 'system', 'aliases': [], 'support_fact_id': retained['facts'][0]['id'],
        'valid_from': None, 'valid_to': None,
    }, headers={'Idempotency-Key': 'cross-fact'})
    assert cross.status_code == 404 and cross.json()['error']['code'] == 'MEMORY_GRAPH_SUPPORT_FACT_NOT_FOUND'
    self_loop = client.post(f'/api/local/memory/banks/{alpha["id"]}/relations', json={
        'subject_entity_id': entities[1]['entity']['id'], 'predicate': 'depends_on',
        'object_entity_id': entities[1]['entity']['id'], 'support_fact_id': retained['facts'][1]['id'],
        'confidence': 0.9, 'occurred_at': '2026-09-20T09:00:00Z', 'valid_from': None, 'valid_to': None,
    }, headers={'Idempotency-Key': 'self-loop'})
    assert self_loop.status_code == 422 and self_loop.json()['error']['code'] == 'MEMORY_GRAPH_REJECTED'
    unknown = client.post(f'/api/local/memory/banks/{alpha["id"]}/entities', json={
        'canonical_name': '未知字段', 'entity_type': 'system', 'aliases': [], 'support_fact_id': retained['facts'][0]['id'],
        'valid_from': None, 'valid_to': None, 'workspace_id': 'other',
    }, headers={'Idempotency-Key': 'unknown-entity'})
    assert unknown.status_code == 422 and cross_fact['entity']['bank_id'] == alpha['id']
    assert graph(client, beta['id'], entities[0]['entity']['id'])['memory_status'] == 'empty'


def test_graph_temporal_supersede_retract_and_delete_propagate(client):
    target, retained, entities, relations = dependency_fixture(client, 'lifecycle-graph')
    start = entities[0]['entity']['id']
    assert graph(client, target['id'], start, max_hops=2)['memory_status'] == 'available'

    expired = graph(client, target['id'], start, max_hops=2, as_of='2037-01-01T00:00:00Z')
    assert expired['memory_status'] == 'empty' and expired['paths'] == []
    before_occurrence = graph(client, target['id'], start, max_hops=2, as_of='2026-09-19T23:59:59Z')
    assert before_occurrence['memory_status'] == 'empty' and before_occurrence['paths'] == []

    replacement = retain(client, target['id'], 'systems:replacement', [{
        **fact('支付系统改为依赖新的风控服务。'), 'supersedes_fact_id': retained['facts'][1]['id'],
    }], 'lifecycle-replacement', content='替代关系的独立来源正文。')
    after_supersede = graph(client, target['id'], start, max_hops=2)
    assert after_supersede['memory_status'] == 'available'
    assert all(path['hop_count'] == 1 for path in after_supersede['paths'])
    assert all(edge['predicate'] != 'depends_on' for path in after_supersede['paths'] for edge in path['edges'])
    with client.app.state.service.store.lock:
        relation_doc = json.loads(client.app.state.service.store.db.execute(
            'SELECT doc FROM memory_relations WHERE id=?', (relations[1]['relation']['id'],)).fetchone()['doc'])
    assert relation_doc['status'] == 'superseded'

    # A separate fully active graph verifies explicit Source delete physically removes dependent objects.
    removed, _, removed_entities, _ = dependency_fixture(client, 'delete-graph')
    deleted = client.delete('/api/local/memory/sources/' + client.app.state.service.store.db.execute(
        'SELECT id FROM memory_sources WHERE bank_id=?', (removed['id'],)).fetchone()['id'],
        headers={'Idempotency-Key': 'delete-graph-source'})
    assert deleted.status_code == 200
    result = deleted.json()
    assert result['deleted_entity_count'] == 3 and result['deleted_relation_count'] == 2
    assert graph(client, removed['id'], removed_entities[0]['entity']['id'], max_hops=2)['memory_status'] == 'empty'
    with client.app.state.service.store.lock:
        entity_count = client.app.state.service.store.db.execute(
            'SELECT count(*) FROM memory_entities WHERE bank_id=?', (removed['id'],)).fetchone()[0]
        relation_count = client.app.state.service.store.db.execute(
            'SELECT count(*) FROM memory_relations WHERE bank_id=?', (removed['id'],)).fetchone()[0]
    assert entity_count == 0 and relation_count == 0


def test_graph_idempotency_retract_and_restart(tmp_path):
    database = tmp_path / 'graph-restart.db'
    with TestClient(create_app(database, False), base_url='http://127.0.0.1') as local:
        target, retained, entities, _ = dependency_fixture(local, 'restart-graph')
        repeat = entity(local, target['id'], '小李', 'person', retained['facts'][0]['id'], 'restart-person-repeat')
        assert repeat['deduplicated'] is True
        retracted = local.post('/api/local/memory/sources/' + retained['source']['id'] + ':retract', json={},
                                headers={'Idempotency-Key': 'retract-graph-source'})
        assert retracted.status_code == 200
        assert retracted.json()['retracted_entity_count'] == 3
        assert retracted.json()['retracted_relation_count'] == 2
        assert graph(local, target['id'], entities[0]['entity']['id'], max_hops=2)['memory_status'] == 'empty'
    with TestClient(create_app(database, False), base_url='http://127.0.0.1') as restarted:
        assert restarted.get('/api/local/memory/runtime').json()['mode'] == 'memory-plane-m3b@1'
        assert graph(restarted, target['id'], entities[0]['entity']['id'], max_hops=2)['memory_status'] == 'empty'


def test_graph_openapi_declares_static_and_runtime_contract(client):
    static = yaml.safe_load((ROOT / 'specs/v1/openapi.yaml').read_text())
    runtime = client.app.openapi()['paths']
    pairs = {
        '/local/memory/banks/{bankId}/entities': '/api/local/memory/banks/{bank_id}/entities',
        '/local/memory/banks/{bankId}/relations': '/api/local/memory/banks/{bank_id}/relations',
        '/local/memory/banks/{bankId}:graph-recall': '/api/local/memory/banks/{bank_id}:graph-recall',
    }
    for static_path, runtime_path in pairs.items():
        assert static_path in static['paths'] and runtime_path in runtime
    assert runtime['/api/local/memory/banks/{bank_id}/entities']['post']['requestBody']['content']['application/json']['schema'] == {
        '$ref': '#/components/schemas/entity_input'}
    assert runtime['/api/local/memory/banks/{bank_id}:graph-recall']['post']['responses']['200']['content']['application/json']['schema'] == {
        '$ref': '#/components/schemas/graph_evidence_bundle'}
