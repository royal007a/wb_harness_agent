import json

import pytest
import yaml
from fastapi.testclient import TestClient

from backend.app import create_app
from backend.service import ROOT


@pytest.fixture
def client(tmp_path):
    with TestClient(create_app(tmp_path / 'memory-entity-catalog.db', False), base_url='http://127.0.0.1') as value:
        yield value


def request(client, method, path, *, body=None, key=None, status=(200, 201)):
    response = client.request(method, path, json=body, headers={'Idempotency-Key': key} if key else {})
    assert response.status_code in status, response.text
    return response.json()


def bank(client, name, key):
    return request(client, 'POST', '/api/local/memory/banks', key=key, body={
        'name': name, 'scope': 'project', 'data_classification': 'Internal', 'retention_days': 90,
    })


def retain(client, bank_id, ref, statements, key, *, occurred_at='2026-09-20T09:00:00Z', content='不应在 Entity Catalog 中回显的原始来源正文。'):
    return request(client, 'POST', f'/api/local/memory/banks/{bank_id}/retain', key=key, body={
        'source': {'source_ref': ref, 'content': content, 'occurred_at': occurred_at, 'data_classification': 'Internal'},
        'facts': [{
            'statement': statement, 'kind': 'fact', 'confidence': 0.9, 'occurred_at': occurred_at,
            'valid_from': occurred_at, 'valid_to': None, 'supersedes_fact_id': None,
        } for statement in statements],
    })


def entity(client, bank_id, name, kind, fact_id, key, *, aliases=None, valid_from=None, valid_to=None):
    return request(client, 'POST', f'/api/local/memory/banks/{bank_id}/entities', key=key, body={
        'canonical_name': name, 'entity_type': kind, 'aliases': aliases or [], 'support_fact_id': fact_id,
        'valid_from': valid_from, 'valid_to': valid_to,
    })['entity']


def resolve(client, bank_id, name, **extra):
    return request(client, 'POST', f'/api/local/memory/banks/{bank_id}:resolve-entity', body={'name': name, **extra})


def catalog_fixture(client, name='catalog'):
    target = bank(client, name, name + '-bank')
    retained = retain(client, target['id'], 'catalog:source', [
        '支付系统由支付团队维护。', '支付项目正在迁移。', '风控服务在生产环境运行。',
    ], name + '-retain')
    payment_system = entity(client, target['id'], '支付系统', 'system', retained['facts'][0]['id'], name + '-system', aliases=['支付', 'Payment System'])
    payment_project = entity(client, target['id'], '支付项目', 'project', retained['facts'][1]['id'], name + '-project', aliases=['支付'])
    risk = entity(client, target['id'], '风控服务', 'system', retained['facts'][2]['id'], name + '-risk')
    return target, retained, payment_system, payment_project, risk


def test_exact_canonical_and_alias_resolution_are_provenanced_and_safe(client):
    target, retained, payment_system, _, _ = catalog_fixture(client)
    canonical = resolve(client, target['id'], '支付系统')
    assert canonical['status'] == 'resolved'
    assert canonical['candidates'][0]['entity_id'] == payment_system['id']
    assert canonical['candidates'][0]['matched_name'] == '支付系统'
    assert canonical['candidates'][0]['support_evidence']['evidence_id'] == retained['facts'][0]['id']
    assert canonical['candidates'][0]['support_evidence']['source_ref'] == 'catalog:source'
    assert '原始来源正文' not in json.dumps(canonical, ensure_ascii=False)
    assert canonical['next_action'] == {'operation': 'memory.graph_recall@1', 'requires_explicit_entity_id': True}
    assert canonical['safety'] == {
        'match_mode': 'exact_canonical_or_alias_casefold', 'automatic_entity_resolution': False,
        'raw_source_content_included': False, 'model_calls': 0,
    }
    alias = resolve(client, target['id'], 'payment system')
    assert alias['status'] == 'resolved'
    assert alias['candidates'][0]['entity_id'] == payment_system['id']
    assert alias['candidates'][0]['matched_name'] == 'Payment System'


def test_ambiguous_alias_is_not_automatically_selected_and_type_can_disambiguate(client):
    target, _, payment_system, payment_project, _ = catalog_fixture(client, 'ambiguous-catalog')
    ambiguous = resolve(client, target['id'], '支付')
    assert ambiguous['status'] == 'ambiguous'
    assert [item['entity_id'] for item in ambiguous['candidates']] == [payment_project['id'], payment_system['id']]
    assert ambiguous['next_action']['requires_explicit_entity_id'] is True
    system = resolve(client, target['id'], '支付', entity_type='system')
    assert system['status'] == 'resolved' and [item['entity_id'] for item in system['candidates']] == [payment_system['id']]
    project = resolve(client, target['id'], '支付', entity_type='project')
    assert project['status'] == 'resolved' and [item['entity_id'] for item in project['candidates']] == [payment_project['id']]


def test_not_found_cross_bank_and_invalid_input_do_not_leak_catalog(client):
    target, _, payment_system, _, _ = catalog_fixture(client, 'isolation-catalog')
    other = bank(client, 'other-catalog', 'other-catalog-bank')
    result = resolve(client, other['id'], '支付系统')
    assert result['status'] == 'not_found' and result['candidates'] == []
    assert payment_system['id'] not in json.dumps(result, ensure_ascii=False)
    missing = resolve(client, target['id'], '不存在的实体')
    assert missing['status'] == 'not_found' and missing['candidates'] == []
    unknown = client.post(f'/api/local/memory/banks/{target["id"]}:resolve-entity', json={'name': '支付系统', 'extra': True})
    assert unknown.status_code == 422 and unknown.json()['error']['code'] == 'VALIDATION_ERROR'
    sensitive = client.post(f'/api/local/memory/banks/{target["id"]}:resolve-entity', json={'name': 'password=not-a-secret'})
    assert sensitive.status_code == 422 and sensitive.json()['error']['code'] == 'MEMORY_ENTITY_CATALOG_REJECTED'


def test_catalog_applies_time_supersede_retract_delete_and_restart(tmp_path):
    database = tmp_path / 'catalog-restart.db'
    with TestClient(create_app(database, False), base_url='http://127.0.0.1') as local:
        target, retained, payment_system, _, _ = catalog_fixture(local, 'lifecycle-catalog')
        assert resolve(local, target['id'], '支付系统')['status'] == 'resolved'
        assert resolve(local, target['id'], '支付系统', as_of='2026-09-19T23:59:59Z')['status'] == 'not_found'
        replacement = retain(local, target['id'], 'catalog:replacement', ['替换后的支付系统事实。'], 'catalog-replacement', content='替代来源。')
        # Write a valid fact supersession directly through the supported Retain contract.
        response = local.post(f'/api/local/memory/banks/{target["id"]}/retain', json={
            'source': {'source_ref': 'catalog:supersede', 'content': '替代事实来源。',
                       'occurred_at': '2026-09-21T09:00:00Z', 'data_classification': 'Internal'},
            'facts': [{
                'statement': '支付系统的旧事实已被替换。', 'kind': 'fact', 'confidence': 0.9,
                'occurred_at': '2026-09-21T09:00:00Z', 'valid_from': '2026-09-21T09:00:00Z', 'valid_to': None,
                'supersedes_fact_id': retained['facts'][0]['id'],
            }],
        }, headers={'Idempotency-Key': 'catalog-supersede'})
        assert response.status_code == 201, response.text
        assert replacement['facts'][0]['status'] == 'active'
        assert resolve(local, target['id'], '支付系统')['status'] == 'not_found'

        # A separately active Entity proves retract and physical Source deletion both remove catalog candidates.
        retractable, retracted_input, _, _, _ = catalog_fixture(local, 'retract-catalog')
        retracted = request(local, 'POST', f'/api/local/memory/sources/{retracted_input["source"]["id"]}:retract',
                            key='catalog-retract', body={})
        assert retracted['retracted_entity_count'] == 3
        assert resolve(local, retractable['id'], '支付系统')['status'] == 'not_found'
        removable, removed_input, _, _, _ = catalog_fixture(local, 'delete-catalog')
        deleted = request(local, 'DELETE', f'/api/local/memory/sources/{removed_input["source"]["id"]}', key='catalog-delete')
        assert deleted['deleted_entity_count'] == 3
        assert resolve(local, removable['id'], '支付系统')['status'] == 'not_found'
        assert payment_system['id']
    with TestClient(create_app(database, False), base_url='http://127.0.0.1') as restarted:
        assert resolve(restarted, target['id'], '支付系统')['status'] == 'not_found'


def test_catalog_openapi_and_runtime_contract(client):
    target, _, _, _, _ = catalog_fixture(client, 'openapi-catalog')
    static = yaml.safe_load((ROOT / 'specs/v1/openapi.yaml').read_text())
    generated = client.app.openapi()
    static_path = '/local/memory/banks/{bankId}:resolve-entity'
    runtime_path = '/api/local/memory/banks/{bank_id}:resolve-entity'
    assert static_path in static['paths'] and runtime_path in generated['paths']
    assert generated['paths'][runtime_path]['post']['requestBody']['content']['application/json']['schema'] == {
        '$ref': '#/components/schemas/entity_resolve_request'}
    assert generated['paths'][runtime_path]['post']['responses']['200']['content']['application/json']['schema'] == {
        '$ref': '#/components/schemas/entity_resolution'}
    runtime = client.get('/api/local/memory/runtime').json()
    assert runtime['entity_catalog'] == {
        'match_mode': 'exact_canonical_or_alias_casefold', 'automatic_entity_resolution': False, 'max_candidates': 16,
    }
    assert resolve(client, target['id'], '风控服务')['status'] == 'resolved'
