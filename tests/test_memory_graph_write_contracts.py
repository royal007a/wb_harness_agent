"""HA-0072: graph write contracts and current support, synthetic local data only."""
import copy
import json
import sqlite3

import pytest
import yaml
from fastapi.testclient import TestClient
from jsonschema import Draft202012Validator
from referencing import Registry, Resource

from backend.app import create_app
from backend import memory
from backend.service import ROOT
from backend.store import dumps
from test_read_surfaces import client, post_bank
from test_memory_write_contracts import body
from test_memory_receipt_deletion import post, world, replay, delete
from test_product_contract_boundaries import snapshot
from test_product_http_contracts import FORMATS


KINDS = ['entity', 'relation']


def documents(c, kind):
    file = ROOT / 'specs/v1/openapi.yaml'
    path = '/local/memory/banks/{bankId}/' + ('entities' if kind == 'entity' else 'relations')
    return [(c.get('/openapi.json').json(), '/api' + path.replace('{bankId}', '{bank_id}'), {}),
            (yaml.safe_load(file.read_text()), path, {'$id': file.as_uri()})]


def validators(c, kind, status='201', request=False):
    sources, resources = {}, []
    for stem in ['memory-graph', 'core-contracts']:
        file = ROOT / 'specs/v1' / (stem + '.schema.json')
        source = json.loads(file.read_text())
        sources[stem] = source
        resources.extend([(file.as_uri(), Resource.from_contents(source)),
                          (source['$id'], Resource.from_contents(source))])
    registry = Registry().with_resources(resources)
    checks = []
    for doc, path, base in documents(c, kind):
        op = doc['paths'][path]['post']
        if request:
            response = op['requestBody']
        else:
            response = op['responses'].get(status, op['responses'].get('default', {}))
            if '$ref' in response:
                response = doc['components']['responses'][response['$ref'].split('/')[-1]]
        schema = response.get('content', {}).get('application/json', {}).get('schema', {})
        check = Draft202012Validator({**doc, **base, **schema}, registry=registry, format_checker=FORMATS)
        assert not check.is_valid({}), ('empty schema', kind, status, request)
        checks.append(check)
    source = sources['memory-graph' if status == '201' or request else 'core-contracts']
    definition = kind + ('_input' if request else '_create_result') if status == '201' or request else 'local_http_error'
    checks.append(Draft202012Validator({**source, '$ref': '#/$defs/' + definition}, format_checker=FORMATS))
    return checks


def check_response(c, kind, response, status):
    assert response.status_code == status, response.text
    for v in validators(c, kind, str(status)):
        v.validate(response.json())
        assert not v.is_valid({**response.json(), 'unexpected': True})
        if status != 201:
            for field, invalid in [('retryable', True), ('code', ''), ('request_id', 'rts_invalid'),
                                   ('details', {'raw': 'not_allowed'})]:
                bad = copy.deepcopy(response.json())
                bad['error'][field] = invalid
                assert not v.is_valid(bad), (kind, status, field)


def setup_graph(c, kind, source_time=None):
    bank = post_bank(c, 'graph72', 'bank72')
    base = '/api/local/memory/banks/' + bank['id']
    request = body('support72')
    if source_time:
        request['source']['occurred_at'] = source_time
    support = post(c, base + '/retain', request, 'support72')
    endpoint = post(c, base + '/retain', body('endpoints72'), 'endpoints72')
    def entity(name):
        return {'canonical_name': name, 'entity_type': 'system', 'aliases': ['alias-' + name],
                'support_fact_id': endpoint['facts'][0]['id']}
    a = post(c, base + '/entities', entity('A72'), 'a72')
    b = post(c, base + '/entities', entity('B72'), 'b72')
    request = {'canonical_name': 'C72', 'entity_type': 'system', 'aliases': ['alias-C72'],
               'support_fact_id': support['facts'][0]['id']} if kind == 'entity' else {
        'subject_entity_id': a['entity']['id'], 'object_entity_id': b['entity']['id'],
        'predicate': 'depends_on', 'support_fact_id': support['facts'][0]['id'],
        'confidence': 0.9, 'occurred_at': '2026-01-01T00:00:00Z'}
    return {'bank': bank, 'support': support, 'endpoint': endpoint, 'request': request,
            'path': base + ('/entities' if kind == 'entity' else '/relations')}


def call(c, w, key='graph72', request=None):
    return c.post(w['path'], json=w['request'] if request is None else request,
                  headers={} if key is None else {'Idempotency-Key': key})


@pytest.mark.parametrize('kind', KINDS)
def test_create_deduplicate_replay_and_normalization(client, kind):
    w = setup_graph(client, kind)
    if kind == 'entity':
        w['request']['canonical_name'] = ' C72 '
        w['request']['aliases'] = [' alias-C72 ', 'ALIAS-C72', 'C72']
    first = call(client, w, 'k' * 128)
    check_response(client, kind, first, 201)
    value = first.json()
    assert value['deduplicated'] is False and value['audit_id'].startswith('memaudit_')
    assert value[kind]['bank_id'] == w['bank']['id']
    assert value[kind]['support_fact_id'] == w['support']['facts'][0]['id']
    if kind == 'entity':
        assert value[kind]['canonical_name'] == 'C72'
        assert value[kind]['aliases'] == ['alias-C72']
    dedup = call(client, w, 'dedup72')
    check_response(client, kind, dedup, 201)
    assert dedup.json() == {**value, 'deduplicated': True, 'audit_id': None}
    before = snapshot(client)
    assert call(client, w, 'k' * 128).json() == value
    assert call(client, w, 'dedup72').json() == dedup.json()
    if kind == 'entity':
        normalized = {**w['request'], 'canonical_name': 'C72', 'aliases': ['alias-C72']}
        assert call(client, w, 'k' * 128, normalized).json() == value
    assert snapshot(client) == before
    assert 'RAW_SOURCE_' not in json.dumps(value)


@pytest.mark.parametrize('kind', KINDS)
@pytest.mark.parametrize('bad', ['new_null_audit', 'dedup_audit', 'missing_field', 'nested_extra'])
def test_success_contract_rejects_independent_bad_instances(client, kind, bad):
    w = setup_graph(client, kind)
    value = call(client, w).json()
    if bad == 'new_null_audit':
        value['audit_id'] = None
    elif bad == 'dedup_audit':
        value['deduplicated'] = True
    elif bad == 'missing_field':
        del value[kind]['support_fact_id']
    else:
        value[kind]['raw_content'] = 'NEVER'
    for v in validators(client, kind):
        assert not v.is_valid(value), (kind, bad)


@pytest.mark.parametrize('kind', KINDS)
@pytest.mark.parametrize('status', [404, 409, 415, 422, 500])
def test_actual_errors_follow_all_three_contracts(client, monkeypatch, kind, status):
    w = setup_graph(client, kind)
    before = snapshot(client)
    if status == 404:
        w['request']['support_fact_id'] = 'memfact_' + '0' * 32
    elif status == 409:
        assert call(client, w).status_code == 201
        before = snapshot(client)
        field = 'canonical_name' if kind == 'entity' else 'confidence'
        w['request'][field] = 'changed72' if kind == 'entity' else 0.1
    elif status == 422:
        w['request']['unexpected'] = True
    elif status == 500:
        def fail(*args):
            raise sqlite3.OperationalError('PRIVATE_DB_PATH72')
        monkeypatch.setattr(client.app.state.service.memory, '_active_support_fact', fail)
        client._transport.raise_server_exceptions = False
    response = client.post(w['path'], content='{}', headers={'Content-Type': 'text/plain',
                           'Idempotency-Key': 'graph72'}) if status == 415 else call(client, w)
    assert response.status_code == status, response.text
    assert snapshot(client) == before
    assert 'PRIVATE_DB_PATH72' not in response.text
    check_response(client, kind, response, status)


@pytest.mark.parametrize('kind', KINDS)
def test_request_schema_and_key_boundaries(client, kind):
    w = setup_graph(client, kind)
    for v in validators(client, kind, request=True):
        v.validate(w['request'])
        for invalid in [[], {}, {**w['request'], 'unknown': True}]:
            assert not v.is_valid(invalid)
    for doc, path, _ in documents(client, kind):
        params = doc['paths'][path]['post']['parameters']
        params = [doc['components']['parameters'][p['$ref'].split('/')[-1]] if '$ref' in p else p for p in params]
        header = next(p for p in params if p.get('name') == 'Idempotency-Key')
        assert header['required'] is True
        v = Draft202012Validator(header['schema'])
        assert v.is_valid('k' * 128)
        assert not v.is_valid('') and not v.is_valid('k' * 129)
    for key in [None, '', 'k' * 129]:
        before = snapshot(client)
        result = call(client, w, key)
        assert result.status_code == 422
        assert snapshot(client) == before
    for invalid in [[], {}, {**w['request'], 'unknown': True}]:
        before = snapshot(client)
        result = call(client, w, request=invalid)
        assert result.status_code == 422
        assert snapshot(client) == before


@pytest.mark.parametrize('kind', KINDS)
def test_future_source_cannot_support_current_graph_write(client, kind):
    w = setup_graph(client, kind, '2099-01-01T00:00:00Z')
    before = snapshot(client)
    result = call(client, w)
    assert result.status_code == 409, result.text
    assert result.json()['error']['code'] == 'MEMORY_GRAPH_SUPPORT_FACT_NOT_ACTIVE'
    assert snapshot(client) == before


@pytest.mark.parametrize('kind', KINDS)
def test_source_time_equality_and_same_key_after_rejection(client, monkeypatch, kind):
    monkeypatch.setattr(memory, 'now', lambda: '2026-10-04T11:59:59Z')
    w = setup_graph(client, kind, '2026-10-04T12:00:00Z')
    before = snapshot(client)
    response = call(client, w)
    assert response.status_code == 409, response.text
    assert snapshot(client) == before
    monkeypatch.setattr(memory, 'now', lambda: '2026-10-04T12:00:00Z')
    response = call(client, w)
    check_response(client, kind, response, 201)
    assert response.json()['deduplicated'] is False


@pytest.mark.parametrize('kind', KINDS)
@pytest.mark.parametrize('mode', ['expired_source', 'future_fact', 'retracted', 'cross_bank'])
def test_invalid_support_fails_without_receipt(client, kind, mode):
    w = setup_graph(client, kind)
    store = client.app.state.service.store
    if mode in {'expired_source', 'future_fact'}:
        table, item, field, value = ('memory_sources', w['support']['source'], 'expires_at', '2000-01-01T00:00:00Z') if mode == 'expired_source' else (
            'memory_facts', w['support']['facts'][0], 'occurred_at', '2099-01-01T00:00:00Z')
        with store.transaction() as db:
            record = json.loads(db.execute('SELECT doc FROM ' + table + ' WHERE id=?', (item['id'],)).fetchone()[0])
            record[field] = value
            db.execute('UPDATE ' + table + ' SET doc=? WHERE id=?', (dumps(record), item['id']))
    elif mode == 'retracted':
        assert client.post('/api/local/memory/sources/' + w['support']['source']['id'] + ':retract',
                           json={}, headers={'Idempotency-Key': 'retract72'}).status_code == 200
    else:
        other = post_bank(client, 'other72', 'other72')
        external = post(client, '/api/local/memory/banks/' + other['id'] + '/retain', body('foreign72'), 'foreign72')
        w['request']['support_fact_id'] = external['facts'][0]['id']
    before = snapshot(client)
    response = call(client, w)
    assert response.status_code == (404 if mode == 'cross_bank' else 409), response.text
    assert snapshot(client) == before


@pytest.mark.parametrize('endpoint', ['subject_entity_id', 'object_entity_id'])
def test_relation_rechecks_endpoint_source_time(client, endpoint):
    w = setup_graph(client, 'relation')
    store = client.app.state.service.store
    # Make the other endpoint independent so both checks are tested separately.
    independent = post(client, w['path'].removesuffix('/relations') + '/entities', {
        'canonical_name': 'Independent72', 'entity_type': 'system', 'aliases': [],
        'support_fact_id': w['support']['facts'][0]['id']}, 'independent72')
    other = 'object_entity_id' if endpoint == 'subject_entity_id' else 'subject_entity_id'
    w['request'][other] = independent['entity']['id']
    with store.transaction() as db:
        record = json.loads(db.execute('SELECT doc FROM memory_sources WHERE id=?',
                                      (w['endpoint']['source']['id'],)).fetchone()[0])
        record['occurred_at'] = '2099-01-01T00:00:00Z'
        db.execute('UPDATE memory_sources SET doc=? WHERE id=?', (dumps(record), record['id']))
    before = snapshot(client)
    result = call(client, w)
    assert result.status_code == 409, result.text
    assert snapshot(client) == before


@pytest.mark.parametrize('kind', KINDS)
@pytest.mark.parametrize('stage', ['audit', 'receipt'])
def test_graph_failure_rolls_back_after_object_write_and_same_key_retries(client, monkeypatch, kind, stage):
    w = setup_graph(client, kind)
    plane = client.app.state.service.memory
    original = plane._audit
    if stage == 'audit':
        def fail(*args):
            raise sqlite3.OperationalError('PRIVATE_INJECT72')
        monkeypatch.setattr(plane, '_audit', fail)
    else:
        with plane.store.transaction() as db:
            db.execute("CREATE TRIGGER graph72_fail BEFORE INSERT ON idempotency WHEN NEW.key='graph72' "
                       "BEGIN SELECT RAISE(ABORT, 'PRIVATE_INJECT72'); END")
    before = snapshot(client)[1]
    client._transport.raise_server_exceptions = False
    failed = call(client, w)
    assert failed.status_code == 500
    assert 'PRIVATE_INJECT72' not in failed.text
    assert snapshot(client)[1] == before
    check_response(client, kind, failed, 500)
    if stage == 'audit':
        monkeypatch.setattr(plane, '_audit', original)
    else:
        with plane.store.transaction() as db:
            db.execute('DROP TRIGGER graph72_fail')
    check_response(client, kind, call(client, w), 201)


@pytest.mark.parametrize('transition', ['retract', 'supersede'])
def test_historical_receipts_then_delete_then_restart(tmp_path, transition):
    path = tmp_path / 'graph72.db'
    with TestClient(create_app(path, False), base_url='http://127.0.0.1') as c:
        w = world(c)
        if transition == 'retract':
            assert c.post('/api/local/memory/sources/' + w['source'] + ':retract', json={},
                          headers={'Idempotency-Key': 'retract72'}).status_code == 200
        else:
            request = body('replacement72')
            request['facts'][0]['supersedes_fact_id'] = w['receipts']['a']['facts'][0]['id']
            post(c, w['base'] + '/retain', request, 'replace72')
        before = snapshot(c)
        for key in ['ea', 'ea-dedup', 'direct', 'direct-dedup']:
            result = replay(c, w, key)
            assert result.json() == w['receipts'][key]
            check_response(c, 'entity' if key.startswith('ea') else 'relation', result, 201)
        assert snapshot(c) == before
        assert delete(c, w).status_code == 200
    with TestClient(create_app(path, False), base_url='http://127.0.0.1') as c:
        before = snapshot(c)
        for key in ['ea', 'ea-dedup', 'direct', 'direct-dedup']:
            result = replay(c, w, key)
            check_response(c, 'entity' if key.startswith('ea') else 'relation', result, 409)
            assert result.json()['error']['code'] == 'MEMORY_RECEIPT_UNAVAILABLE'
        assert replay(c, w, 'keep').json() == w['receipts']['keep']
        assert snapshot(c) == before
