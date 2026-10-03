"""HA-0062: actual Product HTTP instances against published static/dynamic contracts."""
import copy
import hashlib
import json
import re
from datetime import datetime

import pytest
import yaml
from fastapi.testclient import TestClient
from jsonschema import Draft202012Validator, FormatChecker
from referencing import Registry, Resource

from backend.app import create_app
from backend.service import ROOT, local_task


STATIC = ROOT / 'specs/v1/openapi.yaml'
CORE = ROOT / 'specs/v1/core-contracts.schema.json'
FORMATS = FormatChecker()


@FORMATS.checks('date-time', raises=ValueError)
def service_timestamp(value):
    # The optional jsonschema RFC3339 dependency is absent in the pinned venv.
    # Test the service's emitted UTC profile explicitly; not a general RFC3339 validator.
    if not isinstance(value, str):
        return True
    return bool(re.fullmatch(r'\d{4}-\d{2}-\d{2}T(?:[01]\d|2[0-3]):[0-5]\d:[0-5]\d(?:\.\d+)?(?:Z|\+00:00)', value)) and datetime.fromisoformat(value).tzinfo is not None
JSON_OPERATIONS = [
    ('/api/v1/health', 'get', 200),
    ('/api/v1/resources', 'get', 200), ('/api/v1/resources', 'post', 201),
    ('/api/v1/resources/{resource_id}', 'get', 200),
    ('/api/local/research-native/documents', 'post', 201),
    ('/api/local/tasks', 'post', 202), ('/api/v1/tasks', 'post', 202),
    ('/api/v1/tasks', 'get', 200), ('/api/v1/tasks/{task_id}', 'get', 200),
    ('/api/v1/tasks/{task_id}/runs', 'post', 202),
    ('/api/v1/runs/{run_id}', 'get', 200), ('/api/v1/runs/{run_id}:cancel', 'post', 200),
    ('/api/v1/runs/{run_id}/events', 'get', 200),
    ('/api/v1/runs/{run_id}/artifacts', 'get', 200),
    ('/api/v1/tasks/{task_id}/artifacts', 'get', 200),
]


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.delenv('HARNESS_AGENT_RUNTIME', raising=False)
    monkeypatch.delenv('HARNESS_CLAUDE_RESEARCH_RUNTIME', raising=False)
    def forbidden(*args, **kwargs):
        pytest.fail('Product schema checks must not resolve credentials or call a Provider')
    monkeypatch.setattr('backend.research_native.stream_native_research', forbidden)
    with TestClient(create_app(tmp_path / 'product-contracts.db', False), base_url='http://127.0.0.1') as c:
        c.app.state.service.agent_runtime.credentials.resolve = forbidden
        c.app.state.service.agent_runtime.adapters.require = forbidden
        yield c


def documents(client):
    source = json.loads(CORE.read_text())
    registry = Registry().with_resources([
        (CORE.as_uri(), Resource.from_contents(source)),
        (source['$id'], Resource.from_contents(source)),
    ])
    return client.get('/openapi.json').json(), yaml.safe_load(STATIC.read_text()), registry


def static_path(path):
    path = path.removeprefix('/api/v1') if path.startswith('/api/v1/') else path.removeprefix('/api')
    for a, b in [('task_id', 'taskId'), ('run_id', 'runId'), ('resource_id', 'resourceId'), ('artifact_id', 'artifactId')]:
        path = path.replace('{' + a + '}', '{' + b + '}')
    return path


def checker(document, schema, registry, static=False):
    return Draft202012Validator({**document, **schema, **({'$id': STATIC.as_uri()} if static else {})},
                                 registry=registry, format_checker=FORMATS)


def checks(client, path, method, status):
    dynamic, static, registry = documents(client)
    result = []
    for doc, p, is_static in [(dynamic, path, False), (static, static_path(path), True)]:
        operation = doc['paths'][p][method]
        response = operation['responses'].get(str(status), operation['responses'].get('default'))
        if '$ref' in response:
            response = doc['components']['responses'][response['$ref'].split('/')[-1]]
        result.append(checker(doc, response['content']['application/json']['schema'], registry, is_static))
    source = json.loads(CORE.read_text())
    name = result[0].schema['$ref'].split('/')[-1]
    result.append(Draft202012Validator({**source, '$ref': '#/$defs/' + name}, format_checker=FORMATS))
    return result


def assert_instance(client, path, method, response, status=200):
    assert response.status_code == status, response.text
    assert response.headers['content-type'].startswith('application/json')
    for check in checks(client, path, method, status):
        check.validate(response.json())
        assert not check.is_valid({})
        assert not check.is_valid({**response.json(), 'unexpected': True})
    return response.json()


def create_task(client):
    resource = client.post('/api/v1/resources?name=contract.csv', content=b'name,value\nA,2\nB,4\n')
    assert resource.status_code == 201
    body = local_task(resource.json()['id'], '统计表格')
    response = client.post('/api/v1/tasks', json=body, headers={'Idempotency-Key': 'schema-create'})
    assert response.status_code == 202
    return response, body, resource


def test_static_create_response_accepts_actual_shape_without_links(client):
    response, _, _ = create_task(client)
    assert set(response.json()) == {'task', 'initial_run'}
    checks(client, '/api/v1/tasks', 'post', 202)[1].validate(response.json())


def test_static_task_detail_accepts_runs_not_latest_run(client):
    created, _, _ = create_task(client)
    response = client.get('/api/v1/tasks/' + created.json()['task']['id'])
    assert set(response.json()) == {'task', 'runs'}
    checks(client, '/api/v1/tasks/{task_id}', 'get', 200)[1].validate(response.json())


def test_static_cancel_declares_actual_200_not_202(client):
    created, _, _ = create_task(client)
    response = client.post('/api/v1/runs/' + created.json()['initial_run']['id'] + ':cancel')
    assert response.status_code == 200 and response.json()['status'] == 'cancelled'
    _, static, _ = documents(client)
    declared = static['paths']['/runs/{runId}:cancel']['post']
    assert '200' in declared['responses'] and '202' not in declared['responses']
    assert not any(p.get('$ref', '').endswith('IdempotencyKey') for p in declared['parameters'])
    checks(client, '/api/v1/runs/{run_id}:cancel', 'post', 200)[1].validate(response.json())


def test_static_events_declares_actual_json_cursor_not_sse(client):
    created, _, _ = create_task(client)
    response = client.get('/api/v1/runs/' + created.json()['initial_run']['id'] + '/events?after=0')
    assert response.status_code == 200 and set(response.json()) == {'items', 'next_cursor'}
    _, static, _ = documents(client)
    declared = static['paths']['/runs/{runId}/events']['get']
    assert set(declared['responses']['200']['content']) == {'application/json'}
    assert any(p.get('name') == 'after' and p.get('in') == 'query' for p in declared['parameters'])
    assert not any(p.get('name') == 'Last-Event-ID' for p in declared['parameters'])
    checks(client, '/api/v1/runs/{run_id}/events', 'get', 200)[1].validate(response.json())


@pytest.mark.parametrize('path,method,status', JSON_OPERATIONS)
def test_product_dynamic_success_contract_is_not_an_empty_placeholder(client, path, method, status):
    dynamic, _, registry = documents(client)
    schema = dynamic['paths'][path][method]['responses'][str(status)]['content']['application/json']['schema']
    check = checker(dynamic, schema, registry)
    assert not check.is_valid({}), path
    assert not check.is_valid({'arbitrary': 'not a product response'}), path


def test_product_lifecycle_instances_and_downloads_match_both_documents(client):
    assert assert_instance(client, '/api/v1/resources', 'get', client.get('/api/v1/resources')) == {'items': []}
    assert assert_instance(client, '/api/v1/tasks', 'get', client.get('/api/v1/tasks')) == {'items': []}
    health = assert_instance(client, '/api/v1/health', 'get', client.get('/api/v1/health'))
    assert health['model_calls_enabled'] is False
    response, body, uploaded = create_task(client)
    resource = assert_instance(client, '/api/v1/resources', 'post', uploaded, 201)
    assert resource['sha256'] == hashlib.sha256(b'name,value\nA,2\nB,4\n').hexdigest()
    assert resource['row_count'] == 2 and resource['columns'] == ['name', 'value']
    assert assert_instance(client, '/api/v1/resources/{resource_id}', 'get',
                           client.get('/api/v1/resources/' + resource['id'])) == resource
    created = assert_instance(client, '/api/v1/tasks', 'post', response, 202)
    replay = client.post('/api/v1/tasks', json=body, headers={'Idempotency-Key': 'schema-create'})
    assert assert_instance(client, '/api/v1/tasks', 'post', replay, 202) == created
    task, first = created['task']['id'], created['initial_run']['id']
    run_path = '/api/v1/runs/' + first
    assert assert_instance(client, '/api/v1/runs/{run_id}', 'get', client.get(run_path))['status'] == 'queued'
    assert assert_instance(client, '/api/v1/runs/{run_id}/artifacts', 'get',
                           client.get(run_path + '/artifacts')) == {'items': []}
    cancelled = assert_instance(client, '/api/v1/runs/{run_id}:cancel', 'post', client.post(run_path + ':cancel'))
    assert cancelled['status'] == 'cancelled'
    rerun = client.post('/api/v1/tasks/' + task + '/runs', json={'based_on_run_id': first}, headers={'Idempotency-Key': 'next'})
    second = assert_instance(client, '/api/v1/tasks/{task_id}/runs', 'post', rerun, 202)
    assert second['id'] != first and second['based_on_run_id'] == first and second['attempt_number'] == 2
    client.app.state.service.execute(second['id'])
    done_path = '/api/v1/runs/' + second['id']
    done = assert_instance(client, '/api/v1/runs/{run_id}', 'get', client.get(done_path))
    assert done['status'] == 'succeeded'
    assert assert_instance(client, '/api/v1/runs/{run_id}:cancel', 'post', client.post(done_path + ':cancel')) == done
    detail = assert_instance(client, '/api/v1/tasks/{task_id}', 'get', client.get('/api/v1/tasks/' + task))
    assert [(r['id'], r['status']) for r in detail['runs']] == [(second['id'], 'succeeded'), (first, 'cancelled')]
    listing = assert_instance(client, '/api/v1/tasks', 'get', client.get('/api/v1/tasks'))
    assert len(listing['items']) == 1 and listing['items'][0]['latest_run'] == done
    events = assert_instance(client, '/api/v1/runs/{run_id}/events', 'get', client.get(done_path + '/events'))
    assert events['items'][-1]['event_type'] == 'run.succeeded'
    assert events['next_cursor'] == events['items'][-1]['sequence']
    artifacts = assert_instance(client, '/api/v1/runs/{run_id}/artifacts', 'get', client.get(done_path + '/artifacts'))
    assert len(artifacts['items']) == 3
    assert assert_instance(client, '/api/v1/tasks/{task_id}/artifacts', 'get',
                           client.get('/api/v1/tasks/' + task + '/artifacts')) == artifacts
    for artifact in artifacts['items']:
        for download, disposition in [('false', 'inline'), ('true', 'attachment')]:
            response = client.get('/api/v1/artifacts/' + artifact['id'] + '/content?download=' + download)
            assert response.status_code == 200
            assert response.headers['content-type'].split(';')[0] == artifact['media_type']
            assert response.headers['content-disposition'].startswith(disposition + ';')
            assert hashlib.sha256(response.content).hexdigest() == artifact['sha256']


def test_quick_task_pdf_and_legacy_csv_encodings_are_legal_metadata(client):
    csv = '项目,金额\n服务,80\n'.encode('gb18030')
    uploaded = client.post('/api/v1/resources?name=legacy.csv', content=csv)
    resource = assert_instance(client, '/api/v1/resources', 'post', uploaded, 201)
    assert resource['encoding'] == 'gb18030' and resource['row_count'] == 1
    response = client.post('/api/local/tasks', json={'resource_id': resource['id'], 'objective': '分析金额'},
                           headers={'Idempotency-Key': 'quick'})
    assert assert_instance(client, '/api/local/tasks', 'post', response, 202)['initial_run']['status'] == 'queued'
    pdf_bytes = b'%PDF-1.4\nsynthetic registration only\n%%EOF'
    uploaded = client.post('/api/local/research-native/documents?name=public.pdf', content=pdf_bytes,
                           headers={'Content-Type': 'application/pdf'})
    pdf = assert_instance(client, '/api/local/research-native/documents', 'post', uploaded, 201)
    assert pdf['encoding'] == 'binary/pdf' and pdf['data_class'] == 'Public'
    assert pdf['row_count'] == 0 and pdf['columns'] == [] and pdf['sha256'] == hashlib.sha256(pdf_bytes).hexdigest()
    assert assert_instance(client, '/api/v1/resources/{resource_id}', 'get',
                           client.get('/api/v1/resources/' + pdf['id'])) == pdf
    listed = assert_instance(client, '/api/v1/resources', 'get', client.get('/api/v1/resources'))
    assert [r['id'] for r in listed['items']] == [pdf['id'], resource['id']]


@pytest.mark.parametrize('engine', ['research', 'research-agents'])
def test_generic_contracts_accept_research_resources_and_child_runs(client, engine):
    body = {'companies': ['demo_a'], 'concurrency': 3, 'failure_policy': 'continue_with_warning',
            'scenario': 'complete', 'timeout_seconds': 60, 'max_steps': 7}
    if engine == 'research':
        body.update(roles=['financial', 'industry', 'risk'], max_steps=4)
    created = client.post('/api/local/' + engine, json=body, headers={'Idempotency-Key': engine})
    assert created.status_code == 202, created.text
    root = created.json()['initial_run']['id']
    client.app.state.service.execute(root)
    resources = assert_instance(client, '/api/v1/resources', 'get', client.get('/api/v1/resources'))['items']
    assert len(resources) == 3 and all(r['encoding'] == 'utf-8' and r['row_count'] == 1 for r in resources)
    task = created.json()['task']['id']
    detail = assert_instance(client, '/api/v1/tasks/{task_id}', 'get', client.get('/api/v1/tasks/' + task))
    assert len(detail['runs']) == 4
    assert sum(r.get('parent_run_id') == root for r in detail['runs']) == 3
    for run in detail['runs']:
        url = '/api/v1/runs/' + run['id']
        assert assert_instance(client, '/api/v1/runs/{run_id}', 'get', client.get(url))['status'] == 'succeeded'
        assert_instance(client, '/api/v1/runs/{run_id}/events', 'get', client.get(url + '/events'))
        assert assert_instance(client, '/api/v1/runs/{run_id}/artifacts', 'get', client.get(url + '/artifacts'))['items']
    assert assert_instance(client, '/api/v1/tasks', 'get', client.get('/api/v1/tasks'))['items'][0]['latest_run']['id'] == root
    assert assert_instance(client, '/api/v1/tasks/{task_id}/artifacts', 'get',
                           client.get('/api/v1/tasks/' + task + '/artifacts'))['items']


@pytest.mark.parametrize('path,changes', [
    ('/api/v1/resources', {'sha256': 'not-a-hash'}),
    ('/api/v1/resources', {'row_count': -1}),
    ('/api/v1/resources', {'created_at': '2026-02-30T00:00:00Z'}),
    ('/api/v1/resources', {'created_at': 'not-a-time'}),
    ('/api/v1/resources', {'encoding': 'unregistered'}),
    ('/api/v1/resources', {'extra': True}),
    ('/api/v1/tasks', {'status': 'invented'}),
    ('/api/v1/tasks', {'attempt_number': True}),
    ('/api/v1/tasks', {'created_at': 'yesterday'}),
    ('/api/v1/tasks', {'extra': True}),
])
def test_nested_corruption_rejected_by_both_published_schemas(client, path, changes):
    created, _, _ = create_task(client)
    response = client.get(path)
    original = assert_instance(client, path, 'get', response)
    corrupted = copy.deepcopy(original)
    target = corrupted['items'][0] if path.endswith('resources') else corrupted['items'][0]['latest_run']
    target.update(changes)
    assert created.status_code == 202
    for check in checks(client, path, 'get', 200):
        assert not check.is_valid(corrupted), changes


@pytest.mark.parametrize('path,method,request_path,kwargs,status,code', [
    ('/api/v1/resources/{resource_id}', 'get', '/api/v1/resources/res_missing', {}, 404, 'NOT_FOUND'),
    ('/api/v1/tasks/{task_id}', 'get', '/api/v1/tasks/task_missing', {}, 404, 'NOT_FOUND'),
    ('/api/v1/runs/{run_id}', 'get', '/api/v1/runs/run_missing', {}, 404, 'NOT_FOUND'),
    ('/api/v1/artifacts/{artifact_id}/content', 'get', '/api/v1/artifacts/art_missing/content', {}, 404, 'NOT_FOUND'),
    ('/api/v1/tasks', 'post', '/api/v1/tasks', {'json': {}}, 422, 'VALIDATION_ERROR'),
    ('/api/v1/resources', 'post', '/api/v1/resources', {'content': b''}, 413, 'INVALID_RESOURCE'),
    ('/api/local/research-native/documents', 'post', '/api/local/research-native/documents?name=a.pdf',
     {'content': b'%PDF-1.4', 'headers': {'Content-Type': 'text/plain'}}, 415, 'VALIDATION_ERROR'),
    ('/api/v1/health', 'get', '/api/v1/health', {'headers': {'Host': 'evil.example'}}, 403, 'FORBIDDEN'),
])
def test_error_instances_use_actual_envelope_not_fastapi_default(client, path, method, request_path, kwargs, status, code):
    response = client.request(method, request_path, **kwargs)
    assert response.status_code == status, response.text
    assert response.json()['error']['code'] == code
    for check in checks(client, path, method, 'default'):
        check.validate(response.json())
        assert not check.is_valid({'detail': 'FastAPI default is not the service envelope'})
        malformed = copy.deepcopy(response.json())
        malformed['error']['request_id'] = None
        assert not check.is_valid(malformed)


@pytest.mark.parametrize('cursor', ['-1', 'not-an-integer'])
def test_real_cursor_errors_match_documented_422_envelope(client, cursor):
    created, _, _ = create_task(client)
    response = client.get('/api/v1/runs/' + created.json()['initial_run']['id'] + '/events?after=' + cursor)
    assert response.status_code == 422 and response.json()['error']['code'] == 'VALIDATION_ERROR'
    for check in checks(client, '/api/v1/runs/{run_id}/events', 'get', 'default'):
        check.validate(response.json())
    checks(client, '/api/v1/runs/{run_id}/events', 'get', 422)[0].validate(response.json())


def test_binary_success_declarations_and_sample_bytes(client):
    dynamic, static, _ = documents(client)
    for path, media in [('/api/local/sample', 'text/csv'), ('/api/v1/artifacts/{artifact_id}/content', '*/*')]:
        for doc, route in [(dynamic, path), (static, static_path(path))]:
            response = doc['paths'][route]['get']['responses']['200']
            assert set(response['content']) == {media}
            assert response['content'][media]['schema'] == {'type': 'string', 'format': 'binary'}
            assert 'Content-Disposition' in response['headers']
    sample = client.get('/api/local/sample')
    assert sample.status_code == 200 and sample.headers['content-type'].startswith('text/csv')
    assert sample.content == (ROOT / 'examples/sales.csv').read_bytes()


@pytest.mark.parametrize('body,valid', [({}, True), ({'reason': ''}, True),
    ({'reason': '纠正输入后重新分析', 'based_on_run_id': None}, True),
    ({'reason': 'x' * 2000}, True), ({'reason': 'x' * 2001}, False),
    ({'reason': None}, False), ({'unknown': True}, False)])
def test_rerun_request_matches_actual_handler_and_both_documents(client, body, valid):
    created, _, _ = create_task(client)
    dynamic, static, registry = documents(client)
    path = '/api/v1/tasks/{task_id}/runs'
    for doc, p, is_static in [(dynamic, path, False), (static, static_path(path), True)]:
        schema = doc['paths'][p]['post']['requestBody']['content']['application/json']['schema']
        assert checker(doc, schema, registry, is_static).is_valid(body) is valid
    response = client.post('/api/v1/tasks/' + created.json()['task']['id'] + '/runs', json=body,
                           headers={'Idempotency-Key': 'rerun-shape'})
    assert response.status_code == (202 if valid else 422), response.text


def test_event_page_limit_and_cursor_are_checked_on_actual_http(client):
    created, _, _ = create_task(client)
    run_id = created.json()['initial_run']['id']
    store = client.app.state.service.store
    with store.transaction() as db:
        run = store.get('runs', run_id)
        for i in range(501):
            store.event(db, run, 'test.pagination', {'ordinal': i})
    endpoint = '/api/v1/runs/' + run_id + '/events'
    first = assert_instance(client, '/api/v1/runs/{run_id}/events', 'get', client.get(endpoint))
    assert len(first['items']) == 500 and first['next_cursor'] == 500
    assert [e['sequence'] for e in first['items']] == list(range(1, 501))
    second = assert_instance(client, '/api/v1/runs/{run_id}/events', 'get', client.get(endpoint + '?after=500'))
    assert second['items'] and second['items'][0]['sequence'] == 501
    assert second['next_cursor'] == second['items'][-1]['sequence']
    all_events = first['items'] + second['items']
    assert [e['data']['ordinal'] for e in all_events if e['event_type'] == 'test.pagination'] == list(range(501))
    end = assert_instance(client, '/api/v1/runs/{run_id}/events', 'get',
                          client.get(endpoint + '?after=' + str(second['next_cursor'])))
    assert end == {'items': [], 'next_cursor': second['next_cursor']}
    for check in checks(client, '/api/v1/runs/{run_id}/events', 'get', 200):
        assert not check.is_valid({**first, 'items': first['items'] + second['items']})
        assert not check.is_valid({**first, 'next_cursor': -1})
