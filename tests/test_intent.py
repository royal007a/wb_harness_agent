import json
from pathlib import Path
import subprocess
import sys

import pytest
from fastapi.testclient import TestClient

from backend.app import create_app
from backend.intent import IntentRouter, validate_contract


ROOT = Path(__file__).resolve().parents[1]
EVALUATOR = ROOT / 'harness/evaluate_intents.py'
FIXTURE = ROOT / 'fixtures/intent-evaluation-v1.json'


@pytest.fixture
def client(tmp_path):
    with TestClient(create_app(tmp_path / 'intent.db', False), base_url='http://127.0.0.1') as value:
        yield value


def csv_resource(client):
    response = client.post('/api/v1/resources?name=intent.csv', content=b'name,value\nA,2\n')
    assert response.status_code == 201
    return response.json()


def interpret(client, body):
    response = client.post('/api/local/intents:interpret', json=body)
    assert response.status_code == 200, response.text
    return response.json()


def test_ready_response_is_schema_valid_redacted_and_nonexecuting(client):
    resource = csv_resource(client)
    objective = '分析 CSV 的缺失值和数值概况'
    result = interpret(client, {'objective': objective, 'resource_id': resource['id']})
    validate_contract('intent_interpretation', result, status=500)
    assert result['decision'] == 'ready'
    assert result['intent']['id'] == 'local_csv_analysis'
    assert result['route']['creation_mode'] == 'explicit_user_submit'
    assert result['model_calls'] == 0 and objective not in json.dumps(result, ensure_ascii=False)
    assert client.get('/api/v1/tasks').json()['items'] == []


def test_missing_resource_returns_clarification_without_creating_task(client):
    result = interpret(client, {'objective': '检查销售数据质量'})
    assert result['decision'] == 'clarification_required'
    assert result['missing_slots'] == ['resource_id']
    assert result['clarification']['slot_names'] == ['resource_id']
    assert result['route'] is None and client.get('/api/v1/tasks').json()['items'] == []


@pytest.mark.parametrize('objective,code', [
    ('帮我下载百度网盘里的课件', 'INTENT_UNSUPPORTED'), ('   ', 'INTENT_EMPTY_OBJECTIVE'),
])
def test_rejects_unsupported_or_empty_input(client, objective, code):
    result = interpret(client, {'objective': objective})
    assert result['decision'] == 'rejected'
    assert result['intent'] is None and result['route'] is None
    assert result['reason_codes'] == [code]


def test_endpoint_and_local_task_creation_cannot_bypass_preflight(client):
    resource = csv_resource(client)
    rejected = client.post('/api/local/tasks', json={
        'resource_id': resource['id'], 'objective': '帮我下载网盘文件'}, headers={'Idempotency-Key': 'reject-intent'})
    assert rejected.status_code == 422
    assert rejected.json()['error']['code'] == 'INTENT_REJECTED'
    assert client.get('/api/v1/tasks').json()['items'] == []
    ready = client.post('/api/local/tasks', json={
        'resource_id': resource['id'], 'objective': '分析 CSV 数值概况'}, headers={'Idempotency-Key': 'ready-intent'})
    assert ready.status_code == 202, ready.text
    assert ready.json()['task']['objective'] == '分析 CSV 数值概况'


def test_unknown_fields_invalid_resource_and_openapi_contract(tmp_path):
    with TestClient(create_app(tmp_path / 'fresh.db', False), base_url='http://127.0.0.1') as fresh:
        response = fresh.post('/api/local/intents:interpret', json={'objective': '分析数据', 'extra': 1})
        assert response.status_code == 422 and response.json()['error']['code'] == 'VALIDATION_ERROR'
    with TestClient(create_app(tmp_path / 'intent-openapi.db', False), base_url='http://127.0.0.1') as app_client:
        invalid = app_client.post('/api/local/intents:interpret', json={'objective': '分析数据', 'resource_id': 'res_missing'})
        spec = app_client.get('/openapi.json').json()
        assert spec['paths']['/api/local/intents:interpret']['post']['responses']['200']['content']['application/json']['schema'] == {
            '$ref': '#/components/schemas/intent_interpretation'}
    assert invalid.status_code == 404


def test_fixed_fixture_evaluation_is_repeatable_and_redacted(tmp_path):
    output = tmp_path / 'evaluation.json'
    process = subprocess.run([sys.executable, str(EVALUATOR), '--fixture', str(FIXTURE), '--output', str(output)],
                             capture_output=True, text=True, timeout=5)
    assert process.returncode == 0, process.stderr
    report = json.loads(output.read_text())
    assert report['case_count'] == 7 and report['failures'] == []
    assert all(value == 1.0 for value in report['metrics'].values())
    assert '帮我下载百度网盘里的课件' not in output.read_text()


def test_router_rejects_invalid_contract_before_rules():
    with pytest.raises(Exception):
        IntentRouter().interpret({'objective': '分析数据', 'unknown': True})
