import json
from pathlib import Path

from jsonschema import Draft202012Validator

from backend.app import create_app
from backend.framework_catalog import SCHEMA, catalog
from fastapi.testclient import TestClient


def test_catalog_is_machine_valid_and_fail_closed():
    value = catalog()
    assert Draft202012Validator(SCHEMA).is_valid(value)
    assert {item['id'] for item in value['items']} == {'pi', 'claude_agent_sdk', 'langchain', 'langgraph'}
    assert all(item['external_calls'] == 0 for item in value['items'])
    assert all(item['control_plane'] == 'harnessagent' for item in value['items'])
    assert next(item for item in value['items'] if item['id'] == 'pi')['status'] == 'available_offline'
    assert next(item for item in value['items'] if item['id'] == 'claude_agent_sdk')['status'] == 'blocked'


def test_framework_catalog_endpoint_is_read_only_and_explicit(tmp_path):
    with TestClient(create_app(tmp_path / 'catalog.db', run_worker=False), base_url='http://127.0.0.1') as client:
        response = client.get('/api/v1/frameworks')
        assert response.status_code == 200
        payload = response.json()
        assert payload['schema_version'] == 'framework-catalog@1'
        assert all(item['adapter_id'] is None or item['adapter_id'].startswith('engine_') for item in payload['items'])
        assert client.post('/api/v1/frameworks', json={}).status_code == 405


def test_catalog_schema_matches_checked_in_contract():
    path = Path(__file__).resolve().parents[1] / 'specs/v1/framework-catalog.schema.json'
    assert json.loads(path.read_text()) == SCHEMA


def test_static_openapi_declares_catalog_endpoint():
    import yaml

    spec = yaml.safe_load((Path(__file__).resolve().parents[1] / 'specs/v1/openapi.yaml').read_text())
    assert spec['paths']['/frameworks']['get']['operationId'] == 'listFrameworkCatalog'
    assert spec['paths']['/frameworks']['get']['responses']['200']['content']['application/json']['schema'] == {
        '$ref': '#/components/schemas/FrameworkCatalog'
    }
    assert spec['components']['schemas']['FrameworkCatalog']['$ref'].endswith('framework-catalog.schema.json')
