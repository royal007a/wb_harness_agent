"""HA-0069: synthetic evidence lifecycle, never formal data or Provider calls."""
import copy
import json

import pytest
import yaml
from jsonschema import Draft202012Validator
from referencing import Registry, Resource

from backend import memory
from backend.service import ROOT
from test_read_surfaces import client, post_bank
from test_product_contract_boundaries import snapshot
from test_memory_research_read_contracts import OPERATIONS as READS
from test_product_http_contracts import FORMATS


OPERATIONS = [
    ('/api/local/memory/banks/{bank_id}/retain', 'post', '201', 'memory-plane', 'local_http_memory_retained'),
    ('/api/local/memory/sources/{source_id}:retract', 'post', '200', 'memory-plane', 'local_http_memory_retracted'),
    ('/api/local/memory/sources/{source_id}', 'delete', '200', 'memory-plane', 'local_http_memory_deleted'),
]


def body(label='69'):
    return {'source': {'source_ref': 'fixture:' + label, 'content': 'RAW_SOURCE_' + label,
                       'occurred_at': '2026-01-01T00:00:00Z', 'data_classification': 'Internal'},
            'facts': [{'statement': 'Fact ' + label, 'detail': 'Derived detail ' + label,
                       'kind': 'fact', 'confidence': 0.9, 'occurred_at': '2026-01-01T00:00:00Z'}]}


def seed(c, key='retain69'):
    bank = post_bank(c, 'bank69', 'bank69')
    request = body()
    path = '/api/local/memory/banks/' + bank['id'] + '/retain'
    result = c.post(path, json=request, headers={'Idempotency-Key': key})
    assert result.status_code == 201, result.text
    return bank, result.json(), request, path


def check(c, operation, result, status=None):
    validators = contracts(c, operation, status)
    for validator in validators:
        validator.validate(result)
        if not status:
            assert not validator.is_valid({**result, 'unexpected': True})
    return validators


def contracts(c, operation, status=None):
    path, method, success, bundle, name = operation
    sources, resources = {}, []
    for stem in ['memory-plane', 'core-contracts']:
        filename = ROOT / 'specs/v1' / (stem + '.schema.json')
        source = json.loads(filename.read_text())
        sources[stem] = source
        resources.extend([(filename.as_uri(), Resource.from_contents(source)),
                          (source['$id'], Resource.from_contents(source))])
    registry = Registry().with_resources(resources)
    static_file = ROOT / 'specs/v1/openapi.yaml'
    static_path = path.removeprefix('/api').replace('{bank_id}', '{bankId}').replace('{source_id}', '{sourceId}')
    checks = []
    for doc, p, base in [(c.get('/openapi.json').json(), path, {}),
                         (yaml.safe_load(static_file.read_text()), static_path, {'$id': static_file.as_uri()})]:
        responses = doc['paths'][p][method]['responses']
        response = responses.get(status or success, responses.get('default', {}))
        if '$ref' in response:
            response = doc['components']['responses'][response['$ref'].split('/')[-1]]
        schema = response.get('content', {}).get('application/json', {}).get('schema', {})
        validator = Draft202012Validator({**doc, **base, **schema}, registry=registry, format_checker=FORMATS)
        assert not validator.is_valid({}), ('empty response contract', p, method, status)
        checks.append(validator)
    if status:
        bundle, name = 'core-contracts', 'local_http_error'
    assert name in sources[bundle]['$defs'], ('missing source definition', name)
    checks.append(Draft202012Validator({**sources[bundle], '$ref': '#/$defs/' + name}, format_checker=FORMATS))
    return checks


@pytest.mark.parametrize('operation', OPERATIONS, ids=lambda o: o[-1])
def test_write_contracts_are_not_empty(client, operation):
    contracts(client, operation)


@pytest.mark.parametrize('kind', ['utf8', 'deep', 'integer'])
def test_malformed_admission_is_closed_without_breaking_reads(client, tmp_path, monkeypatch, kind):
    path = tmp_path / 'malformed-gate.json'
    raw = {'utf8': b'\xff\xfe{PRIVATE_MARKER', 'deep': b'[' * 10000 + b']' * 10000,
           'integer': b'1' * 10000}[kind]
    path.write_bytes(raw)
    real = memory.semantic_admission_status
    monkeypatch.setattr(memory, 'semantic_admission_status', lambda: real(path))
    client._transport.raise_server_exceptions = False
    before = snapshot(client)
    response = client.get('/api/local/memory/runtime')
    assert response.status_code == 200, response.text
    state = response.json()['semantic_retrieval']
    assert state == {'status': 'invalid_not_admitted', 'admission_enabled': False,
                     'runtime_enabled': False, 'model_calls': 0, 'external_calls': 0,
                     'blocker_count': 1,
                     'error': state['error']}
    assert state['error'] in {'utf8': {'UnicodeDecodeError'},
                              'deep': {'RecursionError', 'schema_validation'},
                              'integer': {'ValueError'}}[kind]
    check(client, READS[0], response.json())
    assert 'PRIVATE_MARKER' not in response.text and str(path) not in response.text
    assert snapshot(client) == before


def test_actual_write_lifecycle_receipts_and_replay(client):
    bank, retained, request, path = seed(client)
    check(client, OPERATIONS[0], retained)
    assert retained['source']['bank_id'] == bank['id'] and not retained['deduplicated']
    assert 'RAW_SOURCE_' not in json.dumps(retained) and 'Derived detail' not in json.dumps(retained)
    assert len(retained['facts']) == 1 and retained['facts'][0]['statement'] == request['facts'][0]['statement']
    assert retained['facts'][0]['source_id'] == retained['source']['id']
    before = snapshot(client)
    replay = client.post(path, json=request, headers={'Idempotency-Key': 'retain69'})
    assert replay.json() == retained and snapshot(client) == before
    dedup = client.post(path, json=request, headers={'Idempotency-Key': 'dedup69'}).json()
    check(client, OPERATIONS[0], dedup)
    assert dedup['source'] == retained['source'] and dedup['facts'] == [] and dedup['audit_id'] is None
    assert dedup['deduplicated'] is True
    source_path = '/api/local/memory/sources/' + retained['source']['id']
    first = client.post(source_path + ':retract', json={}, headers={'Idempotency-Key': 'retract69'})
    assert first.status_code == 200
    check(client, OPERATIONS[1], first.json())
    assert first.json()['retracted_fact_count'] == 1 and first.json()['already_retracted'] is False
    second = client.post(source_path + ':retract', json={}, headers={'Idempotency-Key': 'retract69-second'})
    assert second.json() == {'source_id': retained['source']['id'], 'status': 'retracted',
                             'retracted_fact_count': 0, 'already_retracted': True}
    check(client, OPERATIONS[1], second.json())
    inactive = client.post(path, json=request, headers={'Idempotency-Key': 'dedup69-retracted'}).json()
    check(client, OPERATIONS[0], inactive)
    assert inactive['source']['status'] == 'retracted' and inactive['facts'] == []
    deleted = client.delete(source_path, headers={'Idempotency-Key': 'delete69'})
    assert deleted.status_code == 200
    check(client, OPERATIONS[2], deleted.json())
    assert deleted.json()['deleted_fact_count'] == 1
    before = snapshot(client)
    assert client.delete(source_path, headers={'Idempotency-Key': 'delete69'}).json() == deleted.json()
    assert client.post(source_path + ':retract', json={}, headers={'Idempotency-Key': 'retract69'}).json() == first.json()
    assert client.post(path, json=request, headers={'Idempotency-Key': 'retain69'}).json() == retained
    assert snapshot(client) == before
    counts = client.get('/api/local/memory/banks/' + bank['id']).json()['counts']
    assert counts == {'sources': 0, 'facts': 0}
    # This is canonical deletion, NOT erasure of historical idempotency receipts.
    assert any('Fact 69' in str(row) for row in before[1]['idempotency'])
    missing = client.delete(source_path, headers={'Idempotency-Key': 'delete69-new'})
    assert missing.status_code == 404
    check(client, OPERATIONS[2], missing.json(), '404')
    assert snapshot(client) == before


@pytest.mark.parametrize('stage', ['retain', 'retract', 'delete'])
def test_write_failure_rolls_back_all_tables_and_is_retryable_by_caller(client, monkeypatch, stage):
    bank, retained, _, path = seed(client)
    plane = client.app.state.service.memory
    original_audit = plane._audit
    target = {'retain': 'memory.source.retained', 'retract': 'memory.source.retracted', 'delete': 'memory.source.deleted'}[stage]
    def fail_after_writes(db, bank_id, kind, target_id, metadata):
        if kind == target:
            raise RuntimeError('fixture-failure')
        return original_audit(db, bank_id, kind, target_id, metadata)
    monkeypatch.setattr(plane, '_audit', fail_after_writes)
    client._transport.raise_server_exceptions = False
    request = body('replacement69')
    request['facts'][0]['supersedes_fact_id'] = retained['facts'][0]['id']
    source_path = '/api/local/memory/sources/' + retained['source']['id']
    call = {
        'retain': lambda: client.post(path, json=request, headers={'Idempotency-Key': 'failure69'}),
        'retract': lambda: client.post(source_path + ':retract', json={}, headers={'Idempotency-Key': 'failure69'}),
        'delete': lambda: client.delete(source_path, headers={'Idempotency-Key': 'failure69'}),
    }[stage]
    before = snapshot(client)[1]
    failed = call()
    assert failed.status_code == 500 and failed.json()['error']['code'] == 'INTERNAL_ERROR'
    assert snapshot(client)[1] == before
    assert 'fixture-failure' not in failed.text
    monkeypatch.setattr(plane, '_audit', original_audit)
    success = call()
    assert success.status_code == (201 if stage == 'retain' else 200)
    check(client, OPERATIONS[['retain', 'retract', 'delete'].index(stage)], success.json())
    if stage == 'retain':
        assert success.json()['facts'][0]['supersedes_fact_id'] == retained['facts'][0]['id']
        stored = json.loads(plane.store.db.execute('SELECT doc FROM memory_facts WHERE id=?',
                                                 (retained['facts'][0]['id'],)).fetchone()[0])
        assert stored['status'] == 'superseded'


@pytest.mark.parametrize('operation', range(3))
@pytest.mark.parametrize('key', [None, '', 'x' * 129])
def test_write_key_boundaries_reject_without_writes(client, operation, key):
    _, retained, request, path = seed(client)
    headers = {} if key is None else {'Idempotency-Key': key}
    source_path = '/api/local/memory/sources/' + retained['source']['id']
    before = snapshot(client)
    response = [lambda: client.post(path, json=request, headers=headers),
                lambda: client.post(source_path + ':retract', json={}, headers=headers),
                lambda: client.delete(source_path, headers=headers)][operation]()
    assert response.status_code == 422, response.text
    check(client, OPERATIONS[operation], response.json(), '422')
    assert snapshot(client) == before


def test_request_shapes_and_maximum_key(client):
    _, retained, request, path = seed(client, 'k' * 128)
    before = snapshot(client)
    for bad in [[], {}, {**request, 'unexpected': True}, {**request, 'facts': []},
                {**request, 'source': {**request['source'], 'unexpected': True}}]:
        response = client.post(path, json=bad, headers={'Idempotency-Key': 'shape69'})
        assert response.status_code == 422
        check(client, OPERATIONS[0], response.json(), '422')
    conflict = client.post(path, json=body('changed69'), headers={'Idempotency-Key': 'k' * 128})
    assert conflict.status_code == 409
    check(client, OPERATIONS[0], conflict.json(), '409')
    source_path = '/api/local/memory/sources/' + retained['source']['id']
    for bad in [[], None, {'unexpected': True}]:
        response = client.post(source_path + ':retract', content=json.dumps(bad),
                               headers={'Idempotency-Key': 'retract-shape69', 'Content-Type': 'application/json'})
        assert response.status_code == 422
    assert snapshot(client) == before
    assert client.post(source_path + ':retract', json={}, headers={'Idempotency-Key': 'r' * 128}).status_code == 200
    assert client.delete(source_path, headers={'Idempotency-Key': 'd' * 128}).status_code == 200


@pytest.mark.parametrize('variant', ['source_content', 'detail', 'digest', 'wrong_id', 'time',
                                   'confidence', 'empty_facts', 'dedup_facts', 'missing_audit', 'status'])
def test_retained_negative_instances(client, variant):
    _, retained, _, _ = seed(client)
    bad = copy.deepcopy(retained)
    if variant == 'source_content': bad['source']['content'] = 'raw'
    elif variant == 'detail': bad['facts'][0]['detail'] = 'private'
    elif variant == 'digest': bad['source']['content_sha256'] = 'F' * 64
    elif variant == 'wrong_id': bad['facts'][0]['source_id'] = 'run_wrong'
    elif variant == 'time': bad['source']['expires_at'] = 'not-a-date'
    elif variant == 'confidence': bad['facts'][0]['confidence'] = -1
    elif variant == 'empty_facts': bad['facts'] = []
    elif variant == 'dedup_facts': bad.update(deduplicated=True, audit_id=None)
    elif variant == 'missing_audit': del bad['audit_id']
    elif variant == 'status': bad['source']['status'] = 'deleted'
    for validator in check(client, OPERATIONS[0], retained):
        assert not validator.is_valid(bad), variant


@pytest.mark.parametrize('operation', [1, 2])
def test_lifecycle_receipt_negative_instances(client, operation):
    _, retained, _, _ = seed(client)
    path = '/api/local/memory/sources/' + retained['source']['id']
    result = (client.post(path + ':retract', json={}, headers={'Idempotency-Key': 'neg69'}) if operation == 1
              else client.delete(path, headers={'Idempotency-Key': 'neg69'})).json()
    checks = check(client, OPERATIONS[operation], result)
    for field in result:
        bad = {k: v for k, v in result.items() if k != field}
        assert all(not v.is_valid(bad) for v in checks), field
    prefix = 'retracted' if operation == 1 else 'deleted'
    for field in [prefix + '_fact_count', prefix + '_entity_count', prefix + '_relation_count']:
        assert all(not v.is_valid({**result, field: -1}) for v in checks), field
    assert all(not v.is_valid({**result, 'status': 'active'}) for v in checks)
    if operation == 1:
        assert all(not v.is_valid({**result, 'already_retracted': True}) for v in checks)


def test_previous_review_schema_negative_gaps(client, monkeypatch):
    bank = post_bank(client, 'negative69', 'negative69')
    detail = client.get('/api/local/memory/banks/' + bank['id']).json()
    for validator in check(client, READS[3], detail):
        bad = copy.deepcopy(detail)
        bad['counts']['sources'] = -1
        assert not validator.is_valid(bad)
    plane = client.app.state.service.memory
    monkeypatch.setattr(plane, '_fts_ready', False)
    monkeypatch.setattr(plane, '_fts_error', 'fixture-unavailable')
    runtime = plane.runtime_status()
    for validator in check(client, READS[0], runtime):
        bad = copy.deepcopy(runtime)
        bad['keyword_index']['error'] = None
        assert not validator.is_valid(bad)
        # admitted path isolates external_calls minimum from not_admitted const:0.
        admitted = copy.deepcopy(runtime)
        admitted['semantic_retrieval'].update(status='admitted', admission_enabled=True, error=None, external_calls=0)
        validator.validate(admitted)
        admitted['semantic_retrieval']['external_calls'] = -1
        assert not validator.is_valid(admitted)


def test_admission_decoder_recursion_and_unexpected_failure_are_distinct(tmp_path, monkeypatch):
    path = tmp_path / 'gate.json'
    path.write_text('{}')
    def recursion(*args, **kwargs):
        raise RecursionError('secret path must not escape')
    with monkeypatch.context() as patch:
        patch.setattr(memory.json, 'loads', recursion)
        state = memory.semantic_admission_status(path)
    assert state['error'] == 'RecursionError' and state['runtime_enabled'] is False
    assert 'secret' not in json.dumps(state)
    def unexpected(*args, **kwargs):
        raise RuntimeError('programmer error')
    with monkeypatch.context() as patch:
        patch.setattr(memory.json, 'loads', unexpected)
        with pytest.raises(RuntimeError, match='programmer error'):
            memory.semantic_admission_status(path)


def test_two_consumers_keep_one_source_and_fact(client):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier
    bank = post_bank(client, 'concurrent69', 'concurrent69')
    plane = client.app.state.service.memory
    for same_key in [True, False]:
        barrier = Barrier(2)
        request = body('same' if same_key else 'different')
        def invoke(index):
            barrier.wait(timeout=5)
            return plane.retain(bank['id'], request, 'concurrent69-' + str(same_key) + ('same' if same_key else str(index)))
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(invoke, range(2)))
        if same_key:
            assert results[0] == results[1]
        else:
            assert sorted(r['deduplicated'] for r in results) == [False, True]
        assert results[0]['source']['id'] == results[1]['source']['id']
    assert client.get('/api/local/memory/banks/' + bank['id']).json()['counts'] == {'sources': 2, 'facts': 2}


def test_historical_receipts_persist_across_new_app(client):
    from fastapi.testclient import TestClient
    from backend.app import create_app
    _, retained, request, path = seed(client)
    source_path = '/api/local/memory/sources/' + retained['source']['id']
    response = client.delete(source_path, headers={'Idempotency-Key': 'restart-delete69'})
    assert response.status_code == 200
    store = client.app.state.service.store
    database = store.db.execute('PRAGMA database_list').fetchone()['file']
    client.__exit__(None, None, None)
    with TestClient(create_app(database, False), base_url='http://127.0.0.1') as restarted:
        before = snapshot(restarted)
        assert restarted.delete(source_path, headers={'Idempotency-Key': 'restart-delete69'}).json() == response.json()
        assert restarted.post(path, json=request, headers={'Idempotency-Key': 'retain69'}).json() == retained
        assert snapshot(restarted) == before


def test_delete_stops_on_first_nonempty_asgi_chunk(client):
    import asyncio
    from starlette.requests import Request
    _, retained, _, _ = seed(client)
    route = next(route for route in client.app.routes
                 if getattr(route, 'path', '') == '/api/local/memory/sources/{source_id}' and 'DELETE' in route.methods)
    reads = []
    async def receive():
        reads.append(True)
        if len(reads) > 1:
            raise AssertionError('Must not drain or buffer the body after rejection')
        return {'type': 'http.request', 'body': b'x', 'more_body': True}
    request = Request({'type': 'http', 'method': 'DELETE', 'headers': []}, receive)
    before = snapshot(client)
    from backend.analysis import Problem
    with pytest.raises(Problem) as caught:
        asyncio.run(route.endpoint(retained['source']['id'], request))
    assert caught.value.status == 422 and len(reads) == 1
    assert snapshot(client) == before


@pytest.mark.parametrize('framing', ['chunked', 'false_zero', 'length'])
def test_delete_body_rejected_before_mutation(client, framing):
    _, retained, _, _ = seed(client)
    headers = {'Idempotency-Key': 'delete-body69'}
    if framing == 'false_zero':
        headers['Content-Length'] = '0'
    content = iter([b'{', b'}']) if framing != 'length' else b'{}'
    before = snapshot(client)
    response = client.request('DELETE', '/api/local/memory/sources/' + retained['source']['id'],
                              content=content, headers=headers)
    assert response.status_code == 422, response.text
    assert response.json()['error']['code'] == 'VALIDATION_ERROR'
    assert snapshot(client) == before
