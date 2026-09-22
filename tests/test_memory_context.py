import json

import pytest
import yaml
from fastapi.testclient import TestClient

from backend.app import create_app
from backend.service import ROOT


@pytest.fixture
def client(tmp_path):
    with TestClient(create_app(tmp_path / 'memory-context.db', False), base_url='http://127.0.0.1') as value:
        yield value


def bank(client, name, key):
    response = client.post('/api/local/memory/banks', json={
        'name': name, 'scope': 'project', 'data_classification': 'Internal', 'retention_days': 90,
    }, headers={'Idempotency-Key': key})
    assert response.status_code == 201, response.text
    return response.json()


def retain(client, bank_id, ref, content, facts, key):
    response = client.post(f'/api/local/memory/banks/{bank_id}/retain', json={
        'source': {'source_ref': ref, 'content': content, 'occurred_at': '2026-09-20T10:00:00Z',
                   'data_classification': 'Internal'},
        'facts': facts,
    }, headers={'Idempotency-Key': key})
    assert response.status_code == 201, response.text
    return response.json()


def fact(statement, kind, detail=None, supersedes_fact_id=None, occurred_at='2026-09-20T10:00:00Z'):
    return {
        'statement': statement, 'kind': kind, 'detail': detail, 'confidence': 0.9,
        'occurred_at': occurred_at, 'valid_from': occurred_at, 'valid_to': None,
        'supersedes_fact_id': supersedes_fact_id,
    }


def context(client, bank_id, query, **extra):
    response = client.post(f'/api/local/memory/banks/{bank_id}:context', json={'query': query, **extra})
    assert response.status_code == 200, response.text
    return response.json()


def details(client, bank_id, evidence_ids, **extra):
    response = client.post(f'/api/local/memory/banks/{bank_id}:recall-details', json={
        'evidence_ids': evidence_ids, **extra,
    })
    assert response.status_code == 200, response.text
    return response.json()


def test_context_capsule_preserves_transient_recent_turns_and_catalog_to_detail(client):
    target = bank(client, 'context-project', 'context-bank')
    stored = retain(client, target['id'], 'meeting:2026-09-20', '原始会议逐字稿：该正文只作 Source，不应出现在 Capsule。', [
        fact('本周完成客户演示。', 'objective', '本周五前交付可演示版本，并保留回滚方案。'),
        fact('张三当前偏好下午开会。', 'preference', '最近两次会议均从上午改到下午；上午常被临时会议占用。'),
        fact('当前阶段禁止联网。', 'constraint', '只允许本机 SQLite 与已登记的本地资料；不得打开外网数据源。'),
        fact('资料收集已完成，等待评审。', 'state', '已登记三份资料，尚未批准模型调用。'),
    ], 'context-retain')
    capsule = context(client, target['id'], '张三开会', recent_turns=[
        {'role': 'user', 'content': '本轮只讨论张三的排会时间。'},
        {'role': 'assistant', 'content': '会先检查当前偏好。'},
    ], summary_limit=6, catalog_limit=10)

    assert capsule['schema_version'] == 'memory-context-capsule@1'
    assert capsule['summary']['format'] == 'fact-derived-summary@1'
    assert capsule['summary']['is_model_generated'] is False
    assert capsule['recent_turns'][0]['content'] == '本轮只讨论张三的排会时间。'
    assert capsule['safety'] == {'recent_turns_persisted': False, 'raw_source_content_included': False, 'model_calls': 0}
    assert '原始会议逐字稿' not in json.dumps(capsule, ensure_ascii=False)
    preference = next(item for item in capsule['detail_catalog'] if item['kind'] == 'preference')
    assert preference['detail_available'] is True
    bundle = details(client, target['id'], [preference['evidence_id']])
    assert bundle['memory_status'] == 'available'
    assert bundle['details'][0]['detail'].startswith('最近两次会议')
    assert '原始会议逐字稿' not in json.dumps(bundle, ensure_ascii=False)
    with client.app.state.service.store.lock:
        rows = client.app.state.service.store.db.execute('SELECT doc FROM memory_sources').fetchall()
    assert all('本轮只讨论张三的排会时间。' not in row['doc'] for row in rows)
    assert stored['facts'][1]['id'] == preference['evidence_id']


def test_context_summary_is_structured_and_fts_matches_chinese_terms(client):
    target = bank(client, 'structured-context', 'structured-bank')
    retain(client, target['id'], 'project:context', '受限来源正文。', [
        fact('本周完成客户演示。', 'objective', '演示目标与截止时间。'),
        fact('验收前禁止联网。', 'constraint', '仅允许离线验证。'),
        fact('方案 B 是当前决策。', 'decision', '方案 A 部署复杂，方案 B 支持本周上线。'),
        fact('当前处于评审状态。', 'state', '等待测试与部署证据。'),
    ], 'structured-retain')
    capsule = context(client, target['id'], '本周演示')
    sections = {section['kind']: section['items'] for section in capsule['summary']['sections']}
    assert [item['statement'] for item in sections['objective']] == ['本周完成客户演示。']
    assert capsule['detail_catalog'][0]['kind'] == 'objective'
    runtime = client.get('/api/local/memory/runtime').json()
    assert runtime['mode'] == 'memory-plane-m3b@1'
    assert runtime['keyword_index']['engine'] == 'sqlite-fts5@1'
    assert runtime['vector_index'] is False and runtime['summary_mode'] == 'fact_derived_not_model_generated'


def test_detail_revalidates_supersede_retract_delete_and_bank_isolation(client):
    alpha = bank(client, 'detail-alpha', 'detail-alpha-bank')
    beta = bank(client, 'detail-beta', 'detail-beta-bank')
    old = retain(client, alpha['id'], 'meeting:old', '旧来源正文。', [
        fact('张三此前偏好上午开会。', 'preference', '三个月前的偏好。', occurred_at='2026-06-01T10:00:00Z'),
    ], 'old-retain')
    replacement = retain(client, alpha['id'], 'meeting:new', '新来源正文。', [
        fact('张三当前偏好下午开会。', 'preference', '最近两次会议已改到下午。',
             supersedes_fact_id=old['facts'][0]['id'], occurred_at='2026-09-20T10:00:00Z'),
    ], 'new-retain')
    alpha_capsule = context(client, alpha['id'], '张三开会')
    catalog_ids = alpha_capsule['next_action']['eligible_evidence_ids']
    assert replacement['facts'][0]['id'] in catalog_ids
    assert old['facts'][0]['id'] not in catalog_ids
    stale = details(client, alpha['id'], [old['facts'][0]['id']])
    assert stale['memory_status'] == 'empty' and stale['unavailable_evidence_ids'] == [old['facts'][0]['id']]
    cross = details(client, beta['id'], [replacement['facts'][0]['id']])
    assert cross == {**cross, 'memory_status': 'empty', 'details': [],
                     'unavailable_evidence_ids': [replacement['facts'][0]['id']]}
    retracted = client.post('/api/local/memory/sources/' + replacement['source']['id'] + ':retract', json={},
                             headers={'Idempotency-Key': 'retract-new'})
    assert retracted.status_code == 200
    assert context(client, alpha['id'], '张三开会')['context_status'] == 'empty'
    deleted = client.delete('/api/local/memory/sources/' + old['source']['id'], headers={'Idempotency-Key': 'delete-old'})
    assert deleted.status_code == 200
    with client.app.state.service.store.lock:
        indexed = client.app.state.service.store.db.execute('SELECT count(*) FROM memory_fact_fts').fetchone()[0]
    assert indexed == 0


def test_context_rejects_sensitive_recent_turns_and_rebuilds_fts_after_restart(tmp_path):
    database = tmp_path / 'context-restart.db'
    with TestClient(create_app(database, False), base_url='http://127.0.0.1') as local:
        target = bank(local, 'restart-context', 'restart-context-bank')
        retained = retain(local, target['id'], 'restart:source', '受限来源正文。', [
            fact('下午开会是当前偏好。', 'preference', '最近的明确反馈。'),
        ], 'restart-context-retain')
        rejected = local.post(f'/api/local/memory/banks/{target["id"]}:context', json={
            'query': '下午开会', 'recent_turns': [{'role': 'user', 'content': 'password=not-allowed'}],
        })
        assert rejected.status_code == 422 and rejected.json()['error']['code'] == 'MEMORY_CONTEXT_REJECTED'
        copied_source = local.post(f'/api/local/memory/banks/{target["id"]}/retain', json={
            'source': {'source_ref': 'reject:copy', 'content': '此为不得作为 detail 返回的原始正文。',
                       'occurred_at': '2026-09-20T10:00:00Z', 'data_classification': 'Internal'},
            'facts': [fact('原始正文不能直接作为详情。', 'fact', '此为不得作为 detail 返回的原始正文。')],
        }, headers={'Idempotency-Key': 'reject-raw-detail'})
        assert copied_source.status_code == 422 and copied_source.json()['error']['code'] == 'MEMORY_RETAIN_REJECTED'
        assert context(local, target['id'], '下午开会')['context_status'] == 'available'
    with TestClient(create_app(database, False), base_url='http://127.0.0.1') as restarted:
        runtime = restarted.get('/api/local/memory/runtime').json()
        assert runtime['keyword_index']['ready'] is True
        capsule = context(restarted, target['id'], '下午开会')
        assert capsule['context_status'] == 'available'
        exact = details(restarted, target['id'], [retained['facts'][0]['id']])
        assert exact['details'][0]['detail'] == '最近的明确反馈。'


def test_context_openapi_declares_static_and_runtime_contract(client):
    static = yaml.safe_load((ROOT / 'specs/v1/openapi.yaml').read_text())
    runtime = client.app.openapi()
    pairs = {
        '/local/memory/banks/{bankId}:context': '/api/local/memory/banks/{bank_id}:context',
        '/local/memory/banks/{bankId}:recall-details': '/api/local/memory/banks/{bank_id}:recall-details',
    }
    for static_path, runtime_path in pairs.items():
        assert static_path in static['paths']
        assert runtime_path in runtime['paths']
    assert runtime['paths']['/api/local/memory/banks/{bank_id}:context']['post']['responses']['200']['content']['application/json']['schema'] == {
        '$ref': '#/components/schemas/context_capsule'}
    assert runtime['paths']['/api/local/memory/banks/{bank_id}:recall-details']['post']['requestBody']['content']['application/json']['schema'] == {
        '$ref': '#/components/schemas/detail_recall_request'}
