"""HA-0068: Pi control-plane behavior with a synthetic Adapter, no Provider."""
import copy
import hashlib
import json
import threading
from concurrent.futures import ThreadPoolExecutor

import pytest
import yaml
from fastapi.testclient import TestClient
from jsonschema import Draft202012Validator
from referencing import Registry, Resource

from adapters.pi_contract_review import PiContractReviewResult
from backend.analysis import Problem
from backend.app import create_app
from backend.service import ROOT
from backend.store import dumps
from test_pi_contract_pipeline import pdf_fixture
from test_product_contract_boundaries import snapshot
from test_product_http_contracts import FORMATS, static_path
from test_read_surfaces import client


BASE = '/api/local/pi-contract-review'
MAX = 9223372036854775807
OPS = [
    (BASE, 'post', 202, 'local_http_pi_created'),
    (BASE, 'get', 200, 'local_http_pi_list'),
    (BASE + '/{run_id}', 'get', 200, 'local_http_pi_detail'),
    (BASE + '/{run_id}/events', 'get', 200, 'local_http_pi_events'),
    (BASE + '/{run_id}:gate', 'post', 200, 'local_http_pi_gate_result'),
]


def result(request):
    return PiContractReviewResult({
        'schema_version': 'pi-contract-review@1', 'status': 'needs_human', 'risk_level': 'high',
        'evidence_refs': [f"evidence://{request.resource['id']}/clause-1/page-1"],
        'recommendation': 'Synthetic control-plane finding, not a legal conclusion.',
        'source_resource_id': request.resource['id'],
        'verification': 'sidecar_event_and_evidence_ref_checked',
        'gate': {'status': 'needs_human', 'reason': '高风险条款必须人工确认'},
    }, {'model_calls': 0, 'cost_minor': 0, 'network_calls': 0})


@pytest.fixture
def offline(client, monkeypatch):
    def fake(request, emit, check):
        check()
        emit('run.result.proposed', {'synthetic': True})
        return result(request)
    monkeypatch.setattr(client.app.state.service.pi_contract_review.adapter, 'start_run', fake)
    return client


def create(c, key='create68'):
    response = c.post('/api/local/research-native/documents?name=pi68.pdf',
                      content=pdf_fixture('RAW_SENTINEL_68 public contract'),
                      headers={'Content-Type': 'application/pdf'})
    assert response.status_code == 201, response.text
    body = {'resource_id': response.json()['id'], 'objective': 'Offline control-plane test', 'timeout_seconds': 120}
    response = c.post(BASE, json=body, headers={'Idempotency-Key': key})
    assert response.status_code == 202, response.text
    return response, body


def waiting(c):
    response, body = create(c)
    run_id = response.json()['initial_run']['id']
    c.app.state.service.execute(run_id)
    assert c.get(BASE + '/' + run_id).json()['run']['status'] == 'waiting_approval'
    return run_id, response, body


def gate(c, run_id, decision='pass', key='gate68'):
    return c.post(BASE + '/' + run_id + ':gate', json={'decision': decision, 'reason': 'Synthetic human decision'},
                  headers={'Idempotency-Key': key})


@pytest.mark.parametrize('decision', ['pass', 'reject'])
def test_gate_same_key_replay_is_read_only_after_terminal(offline, decision):
    c = offline
    run_id, _, _ = waiting(c)
    first = gate(c, run_id, decision)
    assert first.status_code == 200, first.text
    before = snapshot(c)
    replay = gate(c, run_id, decision)
    assert replay.status_code == 200, replay.text
    assert replay.content == first.content and snapshot(c) == before
    changed = gate(c, run_id, 'reject' if decision == 'pass' else 'pass')
    assert changed.status_code == 409 and changed.json()['error']['code'] == 'CONFLICT'
    assert snapshot(c) == before


def test_event_page_cursor_never_skips_or_moves_backwards(offline):
    c = offline
    response, _ = create(c)
    run_id = response.json()['initial_run']['id']
    store = c.app.state.service.store
    with store.transaction() as db:
        run = store.get('runs', run_id)
        for _ in range(1000):
            store.event(db, run, 'pi.synthetic', {})
    before = snapshot(c)
    after, sequences, sizes = 0, [], []
    for _ in range(4):
        response = c.get(BASE + '/' + run_id + '/events', params={'after_seq': after})
        assert response.status_code == 200
        page = response.json()
        sizes.append(len(page['events']))
        expected = page['events'][-1]['sequence'] if page['events'] else after
        assert page['next_seq'] == expected
        sequences.extend(e['sequence'] for e in page['events'])
        after = page['next_seq']
    assert sizes == [500, 500, 1, 0] and sequences == list(range(1, 1002))
    assert c.get(BASE + '/' + run_id + '/events', params={'after_seq': MAX}).json()['next_seq'] == MAX
    assert snapshot(c) == before


def test_detail_finds_gate_after_first_five_hundred_events(offline):
    c = offline
    run_id, _, _ = waiting(c)
    store = c.app.state.service.store
    with store.transaction() as db:
        run = store.get('runs', run_id)
        for _ in range(510):
            store.event(db, run, 'pi.synthetic', {})
    assert gate(c, run_id).status_code == 200
    before = snapshot(c)
    detail = c.get(BASE + '/' + run_id).json()
    assert detail['gate']['decision'] == 'pass'
    assert detail['gate_required'] is False
    assert snapshot(c) == before


@pytest.mark.parametrize('late_emit', [False, True])
def test_cancel_wins_before_result_publication(offline, monkeypatch, late_emit):
    c = offline
    service = c.app.state.service
    response, _ = create(c)
    run_id = response.json()['initial_run']['id']
    at_cancel = []
    def delayed(request, emit, check):
        service.pi_contract_review.cancel(run_id)
        at_cancel.append(snapshot(c))
        if late_emit:
            emit('run.result.proposed', {'late': True})
        return result(request)
    monkeypatch.setattr(service.pi_contract_review.adapter, 'start_run', delayed)
    service.execute(run_id)
    assert snapshot(c) == at_cancel[0], 'cancelled Run must not receive late events/artifacts/state'
    detail = c.get(BASE + '/' + run_id).json()
    assert detail['run']['status'] == 'cancelled' and detail['artifacts'] == []


@pytest.mark.parametrize('winner', ['cancel', 'reject'])
def test_gate_rechecks_state_inside_idempotency_transaction(offline, monkeypatch, winner):
    c = offline
    run_id, _, _ = waiting(c)
    service = c.app.state.service
    original = service.idempotent
    before_loser = []
    def interleave(scope, key, body, action):
        if key == 'loser':
            if winner == 'cancel':
                service.pi_contract_review.cancel(run_id)
            else:
                service.pi_contract_review.gate(run_id, {'decision': 'reject', 'reason': 'first'}, 'winner')
            before_loser.append(snapshot(c))
        return original(scope, key, body, action)
    monkeypatch.setattr(service, 'idempotent', interleave)
    late = gate(c, run_id, 'pass', 'loser')
    assert late.status_code == 409 and late.json()['error']['code'] == 'GATE_NOT_OPEN'
    assert snapshot(c) == before_loser[0]


def test_deadline_is_rechecked_before_publishing(offline, monkeypatch):
    c = offline
    service = c.app.state.service
    response, _ = create(c)
    run_id = response.json()['initial_run']['id']
    def delayed(request, emit, check):
        with service.store.transaction() as db:
            run = service.store.get('runs', run_id)
            run['created_at'] = '2000-01-01T00:00:00Z'
            db.execute('UPDATE runs SET doc=? WHERE id=?', (dumps(run), run_id))
        return result(request)
    monkeypatch.setattr(service.pi_contract_review.adapter, 'start_run', delayed)
    service.execute(run_id)
    detail = c.get(BASE + '/' + run_id).json()
    assert detail['run']['status'] == 'failed' and detail['run']['exit_reason'] == 'TIMEOUT'
    assert detail['artifacts'] == []


def validators(c, index, *, error=False, request=False):
    path, method, status, name = OPS[index]
    resources, sources = [], {}
    for stem in ('core-contracts', 'pi-contract-review-runtime'):
        file = ROOT / 'specs/v1' / (stem + '.schema.json')
        source = json.loads(file.read_text())
        sources[stem] = source
        resources.extend([(file.as_uri(), Resource.from_contents(source)),
                          (source['$id'], Resource.from_contents(source))])
    registry = Registry().with_resources(resources)
    static_file = ROOT / 'specs/v1/openapi.yaml'
    result = []
    for document, p, base in [(c.get('/openapi.json').json(), path, {}),
                              (yaml.safe_load(static_file.read_text()), static_path(path), {'$id': static_file.as_uri()})]:
        operation = document['paths'][p][method]
        holder = operation.get('requestBody', {}) if request else operation['responses'].get('default' if error else str(status), {})
        if '$ref' in holder:
            holder = document['components']['responses'][holder['$ref'].split('/')[-1]]
        assert 'application/json' in holder.get('content', {}), ('missing JSON contract', p)
        schema = holder['content']['application/json'].get('schema', {})
        check = Draft202012Validator({**document, **base, **schema}, registry=registry, format_checker=FORMATS)
        assert not check.is_valid({}), ('empty contract accepted', p)
        result.append(check)
    stem = 'core-contracts'
    if error:
        name = 'local_http_error'
    elif request:
        stem, name = 'pi-contract-review-runtime', ('request' if index == 0 else 'gate_decision')
    assert name in sources[stem]['$defs'], ('missing source definition', name)
    result.append(Draft202012Validator({'$defs': sources[stem]['$defs'], '$ref': '#/$defs/' + name}, format_checker=FORMATS))
    return result


def validated(c, index, response, *, error=False):
    assert response.status_code == (OPS[index][2] if not error else response.status_code), response.text
    value = response.json()
    for check in validators(c, index, error=error):
        check.validate(value)
        assert not check.is_valid({**value, 'unexpected': True})
        for field in value:
            # All observed top-level fields of these response wrappers are required.
            if index == 4 and not error:
                break  # Run also has optional fields; core tests cover that contract.
            assert not check.is_valid({k: v for k, v in value.items() if k != field}), field
    return value


@pytest.mark.parametrize('index', range(5))
def test_five_published_pi_contracts_reject_empty(offline, index):
    validators(offline, index)


@pytest.mark.parametrize('decision', ['pass', 'reject', 'cancel'])
def test_lifecycle_instances_artifacts_and_replays_match_three_schemas(offline, monkeypatch, decision):
    c = offline
    service = c.app.state.service
    assert validated(c, 1, c.get(BASE)) == {'items': []}
    response, body = create(c)
    created = validated(c, 0, response)
    run_id = created['initial_run']['id']
    path = BASE + '/' + run_id
    queued = validated(c, 2, c.get(path))
    assert queued['gate'] is None and queued['artifacts'] == [] and queued['gate_required'] is False
    initial = validated(c, 3, c.get(path + '/events'))
    assert len(initial['events']) == 1 and initial['events'][0]['event_type'] == 'run.queued'
    seen = []
    adapter = service.pi_contract_review.adapter
    original = adapter.start_run
    def running(request, emit, check):
        current = c.get(path)
        assert validated(c, 2, current)['run']['status'] == 'running'
        seen.append(current.json())
        return original(request, emit, check)
    monkeypatch.setattr(adapter, 'start_run', running)
    service.execute(run_id)
    pending = validated(c, 2, c.get(path))
    assert seen and pending['run']['status'] == 'waiting_approval' and pending['gate_required'] is True
    if decision == 'cancel':
        response = c.post('/api/v1/runs/' + run_id + ':cancel')
        assert response.status_code == 200 and response.json()['status'] == 'cancelled'
    else:
        response = gate(c, run_id, decision)
        terminal = validated(c, 4, response)
        assert terminal['status'] == ('succeeded' if decision == 'pass' else 'failed')
        assert terminal['exit_reason'] == ('GATE_PASSED' if decision == 'pass' else 'GATE_REJECTED')
    final = validated(c, 2, c.get(path))
    assert final['gate_required'] is False
    if decision == 'cancel':
        assert final['gate'] == pending['gate']
    else:
        assert final['gate']['decision'] == decision
    listed = validated(c, 1, c.get(BASE))
    assert listed['items'] == [final['run']]
    page = validated(c, 3, c.get(path + '/events'))
    assert page['events'][-1]['event_type'] == 'run.' + final['run']['status']
    assert page['next_seq'] == final['run']['latest_sequence']
    assert len(final['artifacts']) == (2 if decision == 'cancel' else 3)
    for artifact in final['artifacts']:
        downloaded = c.get('/api/v1/artifacts/' + artifact['id'] + '/content')
        assert downloaded.status_code == 200
        assert hashlib.sha256(downloaded.content).hexdigest() == artifact['sha256']
        assert len(downloaded.content) == artifact['size_bytes']
        if artifact['name'] == 'pi-contract-review-gate.json':
            record = downloaded.json()
            assert record['decision'] == decision
            assert record['handoff_artifact_id'] == pending['gate']['handoff_artifact_id']
            assert record['evidence_artifact_id'] == pending['gate']['artifact_id']
    before = snapshot(c)
    assert c.post(BASE, json=body, headers={'Idempotency-Key': 'create68'}).json() == created
    if decision != 'cancel':
        assert gate(c, run_id, decision).content == response.content
    def forbidden(*args, **kwargs):
        pytest.fail('GET/replay must not execute Pi')
    monkeypatch.setattr(adapter, 'start_run', forbidden)
    monkeypatch.setattr(service, 'execute', forbidden)
    for url in (BASE, path, path + '/events'):
        assert c.get(url).status_code == 200
    if decision != 'cancel':
        assert gate(c, run_id, decision).status_code == 200
    assert snapshot(c) == before
    assert 'RAW_SENTINEL_68' not in json.dumps([created, queued, pending, final, page])


@pytest.mark.parametrize('index', [0, 4])
def test_requests_headers_and_error_contracts(offline, index):
    c = offline
    run_id, _, body = waiting(c)
    if index == 4:
        body = {'decision': 'pass', 'reason': 'Synthetic human decision'}
    url = BASE if index == 0 else BASE + '/' + run_id + ':gate'
    request_checks = validators(c, index, request=True)
    for check in request_checks:
        check.validate(body)
        for bad in ({}, {**body, 'extra': True}, {**body, next(iter(body)): None}):
            assert not check.is_valid(bad)
    before = snapshot(c)
    for key, bad in [(None, body), ('x' * 129, body), ('extra', {**body, 'extra': True})]:
        response = c.post(url, json=bad, headers={} if key is None else {'Idempotency-Key': key})
        assert response.status_code == 422
        validated(c, index, response, error=True)
        assert snapshot(c) == before
    assert c.post(url, json=body, headers={'Idempotency-Key': 'x' * 128}).status_code == OPS[index][2]
    dynamic = c.get('/openapi.json').json()
    static = yaml.safe_load((ROOT / 'specs/v1/openapi.yaml').read_text())
    for doc, path in [(dynamic, OPS[index][0]), (static, static_path(OPS[index][0]))]:
        op = doc['paths'][path]['post']
        params = [doc['components']['parameters'][p['$ref'].split('/')[-1]] if '$ref' in p else p for p in op['parameters']]
        header = next(p for p in params if p.get('name') == 'Idempotency-Key')
        assert header['required'] is True and header['in'] == 'header'
        assert header['schema']['minLength'] == 1 and header['schema']['maxLength'] == 128
        if '422' in op['responses']:
            assert op['responses']['422']['content'] == op['responses']['default']['content']


@pytest.mark.parametrize('cursor', ['-1', str(MAX + 1), '1.5', 'no', '9' * 400])
def test_pi_cursor_http_rejects_before_store(offline, monkeypatch, cursor):
    c = offline
    response, _ = create(c)
    run_id = response.json()['initial_run']['id']
    calls = []
    original = c.app.state.service.store.events
    def observed(*args, **kwargs):
        calls.append((args, kwargs))
        return original(*args, **kwargs)
    monkeypatch.setattr(c.app.state.service.store, 'events', observed)
    before = snapshot(c)
    response = c.get(BASE + '/' + run_id + '/events', params={'after_seq': cursor})
    assert response.status_code == 422
    assert calls == [], 'invalid HTTP cursor must not reach Store'
    validated(c, 3, response, error=True)
    assert snapshot(c) == before


@pytest.mark.parametrize('cursor', [True, False, 1.0, '1', -1, MAX + 1, None])
def test_pi_cursor_direct_service_rejects_non_int_or_out_of_range(offline, cursor):
    response, _ = create(offline)
    before = snapshot(offline)
    with pytest.raises(Problem) as error:
        offline.app.state.service.pi_contract_review.events(response.json()['initial_run']['id'], cursor)
    assert error.value.code == 'VALIDATION_ERROR' and error.value.status == 422
    assert snapshot(offline) == before


def test_bad_instances_and_parameter_schemas_are_rejected(offline):
    c = offline
    run_id, created, _ = waiting(c)
    values = [created.json(), c.get(BASE).json(), c.get(BASE + '/' + run_id).json(),
              c.get(BASE + '/' + run_id + '/events').json(), gate(c, run_id).json()]
    mutations = [
        (0, lambda v: v['initial_run'].update(status='succeeded')),
        (0, lambda v: v['task']['model_policy'].update(allow_fallback=True)),
        (1, lambda v: v['items'][0].update(selected_engine='engine_mock_analytics')),
        (1, lambda v: v['items'][0].update(parent_run_id='run_parent')),
        (2, lambda v: v.update(gate_required=False)),
        (2, lambda v: v.update(runtime_enabled=True)),
        (2, lambda v: v.update(external_calls=1)),
        (2, lambda v: v.update(gate=None)),
        (2, lambda v: v['gate'].update(decision_options=['pass'])),
        (3, lambda v: v.update(next_seq=MAX + 1)),
        (3, lambda v: v.update(next_seq=-1)),
        (3, lambda v: v.update(events=[v['events'][0]] * 501)),
        (4, lambda v: v.update(exit_reason='GATE_REJECTED')),
        (4, lambda v: v.update(status='waiting_approval')),
    ]
    for index, mutate in mutations:
        for check in validators(c, index):
            check.validate(values[index])
            bad = copy.deepcopy(values[index])
            mutate(bad)
            assert not check.is_valid(bad), (index, bad)
    dynamic = c.get('/openapi.json').json()
    static = yaml.safe_load((ROOT / 'specs/v1/openapi.yaml').read_text())
    for doc, path in [(dynamic, OPS[3][0]), (static, static_path(OPS[3][0]))]:
        query = next(p for p in doc['paths'][path]['get']['parameters'] if p.get('name') == 'after_seq')
        assert query['schema']['minimum'] == 0 and query['schema']['maximum'] == MAX
        assert query['schema']['default'] == 0
        assert doc['paths'][path]['get']['responses']['200']['content'].keys() == {'application/json'}


@pytest.mark.parametrize('same_key', [False, True])
def test_concurrent_gate_requests_commit_only_once(offline, monkeypatch, same_key):
    c = offline
    run_id, _, _ = waiting(c)
    service = c.app.state.service
    original, barrier = service.idempotent, threading.Barrier(2)
    def synchronized(scope, key, body, action):
        barrier.wait(timeout=5)
        return original(scope, key, body, action)
    monkeypatch.setattr(service, 'idempotent', synchronized)
    def decide(number):
        body = {'decision': 'pass' if same_key or number == 0 else 'reject', 'reason': 'concurrent'}
        try:
            return 200, service.pi_contract_review.gate(run_id, body, 'same' if same_key else str(number))
        except Problem as exc:
            return exc.status, exc.code
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(decide, [0, 1]))
    assert sorted(r[0] for r in results) == ([200, 200] if same_key else [200, 409])
    if same_key:
        assert results[0][1] == results[1][1]
    else:
        assert next(r[1] for r in results if r[0] == 409) == 'GATE_NOT_OPEN'
    detail = c.get(BASE + '/' + run_id).json()
    assert len(detail['artifacts']) == 3
    events = service.store.events(run_id)
    assert sum(e['event_type'] == 'gate.decision' for e in events) == 1
    assert sum(e['event_type'] in {'run.succeeded', 'run.failed'} for e in events) == 1


def test_failure_and_restart_keep_historical_receipts(tmp_path, monkeypatch):
    database = tmp_path / 'restart68.db'
    with TestClient(create_app(database, False), base_url='http://127.0.0.1') as first:
        created, _ = create(first)
        service = first.app.state.service
        run_id = created.json()['initial_run']['id']
        def fail(*args):
            raise Problem('PI_SYNTHETIC_FAILED', 'synthetic failure', 409)
        monkeypatch.setattr(service.pi_contract_review.adapter, 'start_run', fail)
        service.execute(run_id)
        failed = validated(first, 2, first.get(BASE + '/' + run_id))
        assert failed['run']['status'] == 'failed' and failed['artifacts'] == []
        monkeypatch.setattr(service.pi_contract_review.adapter, 'start_run', lambda request, *_: result(request))
        created2, _ = create(first, 'second')
        run2 = created2.json()['initial_run']['id']
        service.execute(run2)
        receipt = gate(first, run2).json()
        created3, _ = create(first, 'third')
        run3 = created3.json()['initial_run']['id']
        with service.store.transaction() as db:
            run = service.store.get('runs', run3)
            run['status'] = 'running'
            service.store.event(db, run, 'run.started', {'synthetic_crash': True})
    with TestClient(create_app(database, False), base_url='http://127.0.0.1') as second:
        def forbidden(*args):
            pytest.fail('recovery and replay must not start a sidecar')
        monkeypatch.setattr(second.app.state.service.pi_contract_review.adapter, 'start_run', forbidden)
        second.app.state.service.recover()
        before = snapshot(second)
        assert validated(second, 2, second.get(BASE + '/' + run_id)) == failed
        assert validated(second, 4, gate(second, run2)) == receipt
        recovered = validated(second, 2, second.get(BASE + '/' + run3))
        assert recovered['run']['status'] == 'cancelled' and recovered['artifacts'] == []
        assert validated(second, 1, second.get(BASE))['items'][0]['id'] == run3
        assert snapshot(second) == before


@pytest.mark.parametrize('index', [2, 3, 4])
def test_wrong_engine_and_missing_run_are_not_returned(offline, index):
    c = offline
    resource = c.post('/api/v1/resources?name=other.csv', content=b'a,b\n1,2\n').json()
    response = c.post('/api/local/tasks', json={'resource_id': resource['id'], 'objective': '统计CSV'},
                      headers={'Idempotency-Key': 'other68'})
    assert response.status_code == 202, response.text
    for run_id in [response.json()['initial_run']['id'], 'run_missing']:
        before = snapshot(c)
        response = gate(c, run_id) if index == 4 else c.get(OPS[index][0].replace('{run_id}', run_id))
        assert response.status_code == (409 if index == 4 and run_id != 'run_missing' else 404)
        validated(c, index, response, error=True)
        assert snapshot(c) == before
    assert c.get(BASE).json() == {'items': []}
