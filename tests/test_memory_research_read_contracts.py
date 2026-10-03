"""HA-0066: actual local reads, no execution admission or live credentials."""
import copy
import json

import pytest
import yaml
from fastapi.testclient import TestClient
from jsonschema import Draft202012Validator
from referencing import Registry, Resource

from backend.app import create_app
from backend.service import ROOT
from test_product_http_contracts import FORMATS
from test_product_contract_boundaries import snapshot
from test_read_surfaces import client, post_bank, create_research


STATIC = ROOT / 'specs/v1/openapi.yaml'
OPERATIONS = [
    ('/api/local/memory/runtime', 'get', '200', 'memory-plane', 'local_http_memory_runtime'),
    ('/api/local/memory/banks', 'get', '200', 'memory-plane', 'local_http_memory_bank_list'),
    ('/api/local/memory/banks', 'post', '201', 'memory-plane', 'memory_bank'),
    ('/api/local/memory/banks/{bank_id}', 'get', '200', 'memory-plane', 'local_http_memory_bank_detail'),
    ('/api/local/research', 'get', '200', 'core-contracts', 'local_http_research_demo_list'),
    ('/api/local/research-agents', 'get', '200', 'core-contracts', 'local_http_research_agents_list'),
    ('/api/local/research-native', 'get', '200', 'core-contracts', 'local_http_research_native_list'),
]
ENGINES = ['engine_local_research_demo', 'engine_research_multi_agent_simulation', 'engine_claude_research_native']


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
    dynamic = c.get('/openapi.json').json()
    static = yaml.safe_load(STATIC.read_text())
    validators = []
    for doc, p, base in [(dynamic, path, {}),
                         (static, path.removeprefix('/api').replace('{bank_id}', '{bankId}'), {'$id': STATIC.as_uri()})]:
        assert p in doc['paths'], ('missing published path', p)
        responses = doc['paths'][p][method]['responses']
        response = responses.get(status or success, responses.get('default', {}))
        if '$ref' in response:
            response = doc['components']['responses'][response['$ref'].split('/')[-1]]
        schema = response.get('content', {}).get('application/json', {}).get('schema', {})
        validator = Draft202012Validator({**doc, **base, **schema}, registry=registry, format_checker=FORMATS)
        assert not validator.is_valid({}), ('empty payload accepted by published contract', p, method, status)
        validators.append(validator)
    if status:
        bundle, name = 'core-contracts', 'local_http_error'
    source = sources[bundle]
    assert name in source['$defs'], ('missing source definition', name)
    validators.append(Draft202012Validator({**source, '$ref': '#/$defs/' + name}, format_checker=FORMATS))
    return validators


def validate(c, operation, value):
    validators = contracts(c, operation)
    for check in validators:
        check.validate(value)
        assert not check.is_valid({**value, 'unknown_field': True})
        for field in value:
            assert not check.is_valid({k: v for k, v in value.items() if k != field}), ('missing field', field)
    return validators


@pytest.mark.parametrize('operation', OPERATIONS, ids=lambda o: o[-1])
def test_published_contract_rejects_empty_payload(client, operation):
    contracts(client, operation)


def test_memory_actual_reads_counts_no_content_and_replay(client):
    empty = client.get('/api/local/memory/banks').json()
    assert empty['items'] == []
    validate(client, OPERATIONS[1], empty)
    first = post_bank(client, 'read-contract-first', 'read66-first')
    second = post_bank(client, 'read-contract-second', 'read66-second')
    assert post_bank(client, 'read-contract-first', 'read66-first') == first
    for bank in [first, second]:
        validate(client, OPERATIONS[2], bank)
    retained = client.post('/api/local/memory/banks/' + first['id'] + '/retain', json={
        'source': {'source_ref': 'fixture:contract66', 'content': 'SOURCE_SENTINEL_66',
                   'occurred_at': '2026-01-01T00:00:00Z', 'data_classification': 'Internal'},
        'facts': [{'statement': 'FACT_SENTINEL_66', 'kind': 'fact', 'confidence': 1,
                   'occurred_at': '2026-01-01T00:00:00Z'}],
    }, headers={'Idempotency-Key': 'retain-contract66'})
    assert retained.status_code == 201, retained.text
    before = snapshot(client)
    runtime = client.get('/api/local/memory/runtime').json()
    validate(client, OPERATIONS[0], runtime)
    listing = client.get('/api/local/memory/banks').json()
    validate(client, OPERATIONS[1], listing)
    assert listing == {'items': [second, first], 'runtime': runtime}
    for bank, count in [(first, 1), (second, 0)]:
        result = client.get('/api/local/memory/banks/' + bank['id'])
        assert result.status_code == 200
        validate(client, OPERATIONS[3], result.json())
        assert result.json() == {'bank': bank, 'counts': {'sources': count, 'facts': count}, 'runtime': runtime}
        assert 'SENTINEL_66' not in result.text
    assert snapshot(client) == before
    source_id = retained.json()['source']['id']
    assert client.post('/api/local/memory/sources/' + source_id + ':retract', json={},
                       headers={'Idempotency-Key': 'retract66'}).status_code == 200
    inactive = client.get('/api/local/memory/banks/' + first['id']).json()
    validate(client, OPERATIONS[3], inactive)
    assert inactive['counts'] == {'sources': 1, 'facts': 1}
    assert client.delete('/api/local/memory/sources/' + source_id,
                         headers={'Idempotency-Key': 'delete66'}).status_code == 200
    deleted = client.get('/api/local/memory/banks/' + first['id']).json()
    validate(client, OPERATIONS[3], deleted)
    assert deleted['counts'] == {'sources': 0, 'facts': 0}


@pytest.mark.parametrize('ready', [True, False])
@pytest.mark.parametrize('gate', ['default', 'missing', 'invalid_json', 'invalid_schema', 'admitted'])
def test_memory_runtime_degraded_fts_and_admission_are_valid(client, tmp_path, monkeypatch, ready, gate):
    import backend.memory as memory
    gate_path = tmp_path / 'semantic-gate.json'
    if gate == 'invalid_json':
        gate_path.write_text('{')
    elif gate == 'invalid_schema':
        gate_path.write_text('{}')
    elif gate == 'admitted':
        original = json.loads(memory.SEMANTIC_ADMISSION_STATE.read_text())
        original.update(status='admitted', enabled=True, model_calls=2, external_calls=3,
                        admission_evidence={name: 'fixture:approved' for name in [
                            'corpus_manifest', 'data_egress_review', 'deletion_rebuild_test',
                            'offline_evaluation', 'latency_cost_baseline']})
        gate_path.write_text(json.dumps(original))
    real_status = memory.semantic_admission_status
    if gate != 'default':
        monkeypatch.setattr(memory, 'semantic_admission_status', lambda: real_status(gate_path))
    plane = client.app.state.service.memory
    monkeypatch.setattr(plane, '_fts_ready', ready)
    monkeypatch.setattr(plane, '_fts_error', None if ready else 'no such module: fts5')
    before = snapshot(client)
    result = client.get('/api/local/memory/runtime').json()
    checks = validate(client, OPERATIONS[0], result)
    validate(client, OPERATIONS[1], client.get('/api/local/memory/banks').json())
    assert result['keyword_index']['ready'] is ready
    assert result['keyword_index']['engine'] == ('sqlite-fts5@1' if ready else None)
    expected = 'not_admitted' if gate == 'default' else 'admitted' if gate == 'admitted' else 'invalid_not_admitted'
    assert result['semantic_retrieval']['status'] == expected
    assert result['semantic_retrieval']['runtime_enabled'] is False
    for section, field, value in [('semantic_retrieval', 'runtime_enabled', True),
                                  ('keyword_index', 'engine', None if ready else 'sqlite-fts5@1'),
                                  ('graph_recall', 'max_hops', 3),
                                  ('entity_catalog', 'automatic_entity_resolution', True)]:
        bad = copy.deepcopy(result)
        bad[section][field] = value
        for check in checks:
            assert not check.is_valid(bad), (section, field)
    assert snapshot(client) == before


@pytest.mark.parametrize('mutation', ['missing_runtime', 'unknown', 'wrong_owner', 'wrong_id', 'bad_counts', 'raw_content'])
def test_memory_nested_negative_instances(client, mutation):
    bank = post_bank(client, 'negative66', 'negative66')
    result = client.get('/api/local/memory/banks/' + bank['id']).json()
    checks = validate(client, OPERATIONS[3], result)
    bad = copy.deepcopy(result)
    if mutation == 'missing_runtime':
        del bad['runtime']
    elif mutation == 'unknown':
        bad['runtime']['unexpected'] = True
    elif mutation == 'wrong_owner':
        bad['bank']['owner'] = 'another_user'
    elif mutation == 'wrong_id':
        bad['bank']['id'] = 'run_other'
    elif mutation == 'bad_counts':
        bad['counts']['facts'] = -1
    else:
        bad['bank']['content'] = 'SOURCE_SENTINEL_66'
    for check in checks:
        assert not check.is_valid(bad), mutation


@pytest.mark.parametrize('operation', OPERATIONS)
def test_current_error_envelope_for_reads_and_bank_create(client, operation):
    path, method = operation[:2]
    result = client.request(method, path.replace('{bank_id}', 'membank_missing'), headers={'Origin': 'http://evil.example'})
    assert result.status_code == 403
    for check in contracts(client, operation, 'default'):
        check.validate(result.json())
        for bad in [{}, {'detail': []}, {**result.json(), 'unknown': 1}]:
            assert not check.is_valid(bad)
    if '{bank_id}' in path:
        missing = client.get(path.replace('{bank_id}', 'membank_missing'))
        assert missing.status_code == 404
        for check in contracts(client, operation, 'default'):
            check.validate(missing.json())


@pytest.mark.parametrize('operation,engine', list(zip(OPERATIONS[4:], ENGINES)))
def test_research_lists_actual_lifecycle_and_reject_child_other_engine(client, tmp_path, monkeypatch, operation, engine):
    path = operation[0]
    validate(client, operation, client.get(path).json())
    if path.endswith('research-native'):
        from test_claude_research_runtime import enabled_env, REQUEST, PUBLIC_PDF
        enabled_env(monkeypatch, tmp_path)
        resource = client.post('/api/local/research-native/documents?name=report.pdf', content=PUBLIC_PDF,
                               headers={'Content-Type': 'application/pdf'})
        assert resource.status_code == 201
        body = {**REQUEST, 'report_resource_id': resource.json()['id']}
        first_response = client.post(path, json=body, headers={'Idempotency-Key': 'native66'})
        assert first_response.status_code == 202, first_response.text
        first = first_response.json()
    else:
        first, body = create_research(client, path, 'first66')
    root = first['initial_run']['id']
    detail = client.get(path + '/' + root).json()
    child = detail['children'][0]['run']
    before = snapshot(client)
    listed = client.get(path).json()
    assert listed == {'items': [detail['run']]}
    checks = validate(client, operation, listed)
    for check in checks:
        for field, value in [('selected_engine', 'engine_mock_analytics'), ('parent_run_id', root),
                             ('status', 'finished'), ('id', 'rts_wrong')]:
            bad = copy.deepcopy(listed)
            bad['items'][0][field] = value
            assert not check.is_valid(bad), field
        assert not check.is_valid({'items': [child]})
        missing_parent = copy.deepcopy(listed)
        missing_parent['items'][0].pop('parent_run_id', None)
        check.validate(missing_parent)
        missing_parent['items'][0]['parent_run_id'] = None
        check.validate(missing_parent)
    assert snapshot(client) == before
    if not path.endswith('research-native'):
        client.app.state.service.execute(root)
        assert client.get(path).json()['items'][0]['status'] == 'succeeded'
    cancelled = client.post('/api/v1/runs/' + root + ':cancel')
    assert cancelled.status_code == 200
    next_run = client.post('/api/v1/tasks/' + first['task']['id'] + '/runs', json={},
                           headers={'Idempotency-Key': 'rerun66'})
    assert next_run.status_code == 202, next_run.text
    monkeypatch.delenv('HARNESS_CLAUDE_RESEARCH_RUNTIME', raising=False)
    monkeypatch.delenv('HARNESS_CLAUDE_RESEARCH_EXTERNAL_DATA', raising=False)
    saved = client.get(path).json()
    validate(client, operation, saved)
    assert [r['id'] for r in saved['items']] == [next_run.json()['id'], root]
    before = snapshot(client)
    assert client.get(path).json() == saved
    assert snapshot(client) == before


def test_schema_required_fields_and_bindings_match_static_dynamic(client):
    dynamic = client.get('/openapi.json').json()
    static = yaml.safe_load(STATIC.read_text())
    for path, method, status, bundle, name in OPERATIONS:
        d = dynamic['paths'][path][method]
        s = static['paths'][path.removeprefix('/api').replace('{bank_id}', '{bankId}')][method]
        assert d['responses'][status]['content'] == {'application/json': {'schema': {'$ref': '#/components/schemas/' + name}}}
        assert s['responses'][status]['content'] == {'application/json': {'schema': {'$ref': './' + bundle + '.schema.json#/$defs/' + name}}}
        assert d['responses']['default']['content']['application/json']['schema'] == {'$ref': '#/components/schemas/local_http_error'}
        assert s['responses']['default'] == {'$ref': '#/components/responses/LocalProductError'}
        if '422' in d['responses']:
            assert d['responses']['422']['content']['application/json']['schema'] == {'$ref': '#/components/schemas/local_http_error'}
        if '{bank_id}' in path:
            for op, param in [(d, 'bank_id'), (s, 'bankId')]:
                assert any(p.get('name') == param and p.get('in') == 'path' and p.get('required') for p in op['parameters'])


def test_read_contracts_survive_restart_with_gates_closed(tmp_path, monkeypatch):
    from test_claude_research_runtime import enabled_env, REQUEST, PUBLIC_PDF
    def forbidden(*args, **kwargs):
        pytest.fail('Historical read must not execute a Run, resolve credentials, or stream native SDK')
    monkeypatch.setattr('backend.research_native.stream_native_research', forbidden)
    database = tmp_path / 'restart66.db'
    enabled_env(monkeypatch, tmp_path)
    with TestClient(create_app(database, False), base_url='http://127.0.0.1') as first:
        bank = post_bank(first, 'restart66', 'restart66')
        create_research(first, '/api/local/research', 'restart-demo')
        create_research(first, '/api/local/research-agents', 'restart-agents')
        pdf = first.post('/api/local/research-native/documents?name=report.pdf', content=PUBLIC_PDF,
                         headers={'Content-Type': 'application/pdf'}).json()
        result = first.post('/api/local/research-native', json={**REQUEST, 'report_resource_id': pdf['id']},
                            headers={'Idempotency-Key': 'restart-native'})
        assert result.status_code == 202, result.text
        saved = {op[0]: first.get(op[0]).json() for op in OPERATIONS if op[1] == 'get' and '{' not in op[0]}
    monkeypatch.delenv('HARNESS_CLAUDE_RESEARCH_RUNTIME', raising=False)
    monkeypatch.delenv('HARNESS_CLAUDE_RESEARCH_EXTERNAL_DATA', raising=False)
    with TestClient(create_app(database, False), base_url='http://127.0.0.1') as second:
        service = second.app.state.service
        monkeypatch.setattr(service, 'execute', forbidden)
        service.agent_runtime.credentials.resolve = forbidden
        service.agent_runtime.adapters.require = forbidden
        before = snapshot(second)
        for op in OPERATIONS:
            if op[1] != 'get':
                continue
            value = second.get(op[0].replace('{bank_id}', bank['id'])).json()
            validate(second, op, value)
            if op[0] in saved:
                assert value == saved[op[0]]
        assert snapshot(second) == before
