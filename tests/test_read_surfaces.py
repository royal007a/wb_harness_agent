"""HA-0061: behavior checks for previously unobserved read surfaces.

No live Provider or formal DB. OpenAPI placeholders remain an explicit gap.
"""
import hashlib
import json

import pytest
from fastapi.testclient import TestClient
from jsonschema import Draft202012Validator, FormatChecker

from backend.analysis import parse_csv
from backend.app import create_app
from backend.service import ROOT, validate
from backend.memory import CONTRACT as MEMORY_CONTRACT


CSV = b'label,value\nRAW_SOURCE_SENTINEL,7\n'
PDF = b'%PDF-1.4\nRAW_PDF_SENTINEL'
RESEARCH = {
    'companies': ['demo_a'], 'concurrency': 3, 'failure_policy': 'continue_with_warning',
    'scenario': 'complete', 'timeout_seconds': 60, 'max_steps': 7,
}


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.delenv('HARNESS_AGENT_RUNTIME', raising=False)
    monkeypatch.delenv('HARNESS_CLAUDE_RESEARCH_RUNTIME', raising=False)
    monkeypatch.delenv('HARNESS_CLAUDE_RESEARCH_EXTERNAL_DATA', raising=False)
    def forbidden(*args, **kwargs):
        pytest.fail('Read probes must not call a native SDK or resolve credentials')
    monkeypatch.setattr('backend.research_native.stream_native_research', forbidden)
    with TestClient(create_app(tmp_path / 'reads.db', False), base_url='http://127.0.0.1') as value:
        value.app.state.service.agent_runtime.credentials.resolve = forbidden
        value.app.state.service.agent_runtime.adapters.require = forbidden
        yield value


def get(client, path):
    response = client.get(path)
    assert response.status_code == 200, response.text
    return response


def upload(client, name='reads.csv', content=CSV):
    response = client.post('/api/v1/resources', params={'name': name}, content=content)
    assert response.status_code == 201, response.text
    return response.json()


def post_bank(client, name, key):
    body = {'name': name, 'scope': 'project', 'data_classification': 'Internal', 'retention_days': 90}
    response = client.post('/api/local/memory/banks', json=body, headers={'Idempotency-Key': key})
    assert response.status_code == 201, response.text
    return response.json()


def assert_resource_metadata(resource, raw, name, encoding, rows, columns, classification):
    assert set(resource) == {'id', 'name', 'sha256', 'size_bytes', 'data_class', 'row_count',
                             'columns', 'encoding', 'created_at'}
    sha = hashlib.sha256(raw).hexdigest()
    assert resource['id'] == 'res_' + sha and resource['sha256'] == sha
    assert resource['size_bytes'] == len(raw) and resource['name'] == name
    assert resource['encoding'] == encoding and resource['row_count'] == rows
    assert resource['columns'] == columns and resource['data_class'] == classification
    FormatChecker().check(resource['created_at'], 'date-time')


def test_resources_list_detail_dedup_order_and_no_raw_content(client):
    assert get(client, '/api/v1/resources').json() == {'items': []}
    first = upload(client)
    assert_resource_metadata(first, CSV, 'reads.csv', 'utf-8-sig', 1, ['label', 'value'], 'Internal')
    # Content addressing preserves the first registration, even if renamed.
    assert upload(client, 'renamed.csv') == first
    response = client.post('/api/local/research-native/documents?name=public.pdf', content=PDF,
                           headers={'Content-Type': 'application/pdf'})
    assert response.status_code == 201, response.text
    second = response.json()
    assert_resource_metadata(second, PDF, 'public.pdf', 'binary/pdf', 0, [], 'Public')
    before = client.app.state.service.store.db.total_changes
    listing = get(client, '/api/v1/resources')
    assert listing.json() == {'items': [second, first]}
    for resource in (first, second):
        detail = get(client, '/api/v1/resources/' + resource['id'])
        assert detail.json() == resource
        assert 'RAW_' not in detail.text
    assert 'RAW_' not in listing.text
    assert client.app.state.service.store.db.total_changes == before
    missing = client.get('/api/v1/resources/res_' + '0' * 64)
    assert missing.status_code == 404 and missing.json()['error']['code'] == 'NOT_FOUND'
    assert get(client, '/api/v1/resources').json() == {'items': [second, first]}


def test_banks_list_detail_order_no_retained_content(client):
    assert get(client, '/api/local/memory/banks').json()['items'] == []
    first, second = post_bank(client, 'alpha-read61', 'bank-a'), post_bank(client, 'beta-read61', 'bank-b')
    assert post_bank(client, 'alpha-read61', 'bank-a') == first
    retained = client.post('/api/local/memory/banks/' + first['id'] + '/retain', json={
        'source': {'source_ref': 'fixture:read61', 'content': 'SOURCE_SENTINEL_61',
                   'occurred_at': '2026-10-01T09:00:00Z', 'data_classification': 'Internal'},
        'facts': [{'statement': 'FACT_SENTINEL_61', 'kind': 'fact', 'confidence': 1,
                   'occurred_at': '2026-10-01T09:00:00Z', 'valid_from': None, 'valid_to': None,
                   'supersedes_fact_id': None}],
    }, headers={'Idempotency-Key': 'retain-a'})
    assert retained.status_code == 201, retained.text
    before = client.app.state.service.store.db.total_changes
    listing = get(client, '/api/local/memory/banks')
    assert set(listing.json()) == {'items', 'runtime'}
    assert listing.json()['items'] == [second, first]
    validator = Draft202012Validator({'$ref': '#/$defs/memory_bank', '$defs': MEMORY_CONTRACT['$defs']},
                                     format_checker=FormatChecker())
    for bank in listing.json()['items']:
        validator.validate(bank)
        assert not validator.is_valid({**bank, 'unexpected': True})
        assert bank['owner'] == 'local_admin' and bank['workspace_id'] == 'ws_local'
        detail = get(client, '/api/local/memory/banks/' + bank['id']).json()
        assert detail['bank'] == bank
        assert detail['counts'] == ({'sources': 1, 'facts': 1} if bank == first else {'sources': 0, 'facts': 0})
    assert 'SENTINEL_61' not in listing.text and 'fixture:read61' not in listing.text
    assert listing.json()['runtime'] == get(client, '/api/local/memory/runtime').json()
    assert client.app.state.service.store.db.total_changes == before


def test_resource_and_bank_lists_survive_actual_app_restart(tmp_path):
    database = tmp_path / 'persisted-reads.db'
    with TestClient(create_app(database, False), base_url='http://127.0.0.1') as first:
        resource = upload(first)
        bank = post_bank(first, 'persistent-bank61', 'persist-bank')
    with TestClient(create_app(database, False), base_url='http://127.0.0.1') as second:
        assert get(second, '/api/v1/resources').json() == {'items': [resource]}
        assert get(second, '/api/v1/resources/' + resource['id']).json() == resource
        assert get(second, '/api/local/memory/banks').json()['items'] == [bank]


def create_research(client, path, key):
    body = dict(RESEARCH)
    if path == '/api/local/research':
        body.update(roles=['financial', 'industry', 'risk'], max_steps=4)
    response = client.post(path, json=body, headers={'Idempotency-Key': key})
    assert response.status_code == 202, response.text
    return response.json(), body


@pytest.mark.parametrize('path,engine', [
    ('/api/local/research', 'engine_local_research_demo'),
    ('/api/local/research-agents', 'engine_research_multi_agent_simulation'),
])
def test_research_lists_only_own_roots_and_follow_current_state(client, path, engine):
    assert get(client, path).json() == {'items': []}
    other_path = '/api/local/research-agents' if path == '/api/local/research' else '/api/local/research'
    first, body = create_research(client, path, 'root-first')
    second, _ = create_research(client, path, 'root-second')
    foreign, _ = create_research(client, other_path, 'other-engine')
    replay = client.post(path, json=body, headers={'Idempotency-Key': 'root-first'})
    assert replay.status_code == 202 and replay.json() == first
    first_id, second_id = first['initial_run']['id'], second['initial_run']['id']
    listing = get(client, path).json()
    assert set(listing) == {'items'}
    assert [r['id'] for r in listing['items']] == [second_id, first_id]
    children = [child['run']['id'] for child in get(client, path + '/' + first_id).json()['children']]
    assert children and not set(children).intersection(r['id'] for r in listing['items'])
    assert foreign['initial_run']['id'] not in json.dumps(listing)
    assert get(client, '/api/local/research-native').json() == {'items': []}
    for run in listing['items']:
        validate('run', run)
        assert run['selected_engine'] == engine and run.get('parent_run_id') is None
        assert run == get(client, path + '/' + run['id']).json()['run']
    client.app.state.service.execute(first_id)  # Deterministic fixed-function engines only.
    cancelled = client.post('/api/v1/runs/' + second_id + ':cancel')
    assert cancelled.status_code == 200 and cancelled.json()['status'] == 'cancelled'
    before = client.app.state.service.store.db.total_changes
    current = get(client, path).json()['items']
    assert [r['status'] for r in current] == ['cancelled', 'succeeded']
    for run in current:
        assert run == get(client, path + '/' + run['id']).json()['run']
    assert client.app.state.service.store.db.total_changes == before


def test_sample_download_and_health_do_not_create_product_state(client):
    store = client.app.state.service.store
    before = store.db.total_changes
    response = get(client, '/api/local/sample')
    assert response.content == (ROOT / 'examples/sales.csv').read_bytes()
    assert response.headers['content-type'].startswith('text/csv')
    assert response.headers['content-disposition'] == 'attachment; filename="sales.csv"'
    headers, rows, _ = parse_csv(response.content)
    assert headers and rows
    health = get(client, '/api/v1/health')
    # Static process response, NOT a live Provider counter or release identity.
    assert health.json() == {'status': 'ok', 'version': '0.1.0', 'mode': 'local_single_user',
                             'model_calls_enabled': False}
    assert store.db.total_changes == before
    assert get(client, '/api/v1/resources').json() == {'items': []}
    registered = upload(client, 'sample.csv', response.content)
    assert registered['columns'] == headers and registered['row_count'] == len(rows)


@pytest.mark.parametrize('path', ['/openapi.json', '/static/app.js'])
def test_head_matches_get_metadata_without_body_or_database_writes(client, path):
    before = client.app.state.service.store.db.total_changes
    expected = get(client, path)
    head = client.head(path)
    assert head.status_code == 200 and head.content == b''
    for name in ('content-type', 'content-length', 'cache-control', 'x-content-type-options'):
        assert head.headers[name] == expected.headers[name]
    assert int(head.headers['content-length']) == len(expected.content)
    assert client.app.state.service.store.db.total_changes == before


@pytest.mark.parametrize('path', ['/static/missing61.js', '/static/%2e%2e/backend/app.py', '/static/%2e%2e/AGENTS.md'])
def test_static_get_and_head_reject_missing_or_outside_paths(client, path):
    for method in ('GET', 'HEAD'):
        response = client.request(method, path)
        assert response.status_code == 404
        if method == 'HEAD':
            assert response.content == b''


@pytest.mark.parametrize('method,path', [
    ('GET', '/api/local/memory/banks'), ('GET', '/api/local/research'),
    ('GET', '/api/local/research-agents'), ('GET', '/api/local/research-native'),
    ('GET', '/api/local/sample'), ('GET', '/api/v1/health'), ('GET', '/api/v1/resources'),
    ('GET', '/api/v1/resources/res_' + '0' * 64),
    ('GET', '/api/v1/runs/run_missing/replans'), ('HEAD', '/openapi.json'), ('HEAD', '/static/app.js'),
])
@pytest.mark.parametrize('headers,code,status', [
    ({'Host': 'attacker.invalid'}, 'FORBIDDEN', 403),
    ({'Origin': 'http://attacker.invalid'}, 'FORBIDDEN', 403),
    ({'Sec-Fetch-Site': 'cross-site'}, 'FORBIDDEN', 403),
    ({'X-Forwarded-Prefix': '/unsupported'}, 'INVALID_PROXY_PREFIX', 400),
])
def test_read_surfaces_keep_local_boundary(client, method, path, headers, code, status):
    before = client.app.state.service.store.db.total_changes
    response = client.request(method, path, headers=headers)
    assert response.status_code == status
    if method == 'GET':
        assert response.json()['error']['code'] == code
    else:
        assert response.content == b''
    assert client.app.state.service.store.db.total_changes == before
