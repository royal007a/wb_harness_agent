"""HA-0065: independently chosen wire boundaries, no live service or Provider."""
import copy
import pytest

from backend.analysis import Problem
from test_product_http_contracts import (
    client, create_task, documents, checks, checker, static_path, JSON_OPERATIONS,
)


MAX_CURSOR = 9223372036854775807
EVENTS = '/api/v1/runs/{run_id}/events'


def snapshot(client):
    store = client.app.state.service.store
    with store.transaction() as db:
        tables = [r['name'] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")]
        return db.total_changes, {t: [tuple(row) for row in db.execute('SELECT * FROM ' + t)] for t in tables}


def cursor_checks(client):
    dynamic, static, registry = documents(client)
    return [checker(doc, next(p['schema'] for p in doc['paths'][path]['get']['parameters']
                             if p.get('name') == 'after'), registry, is_static)
            for doc, path, is_static in [(dynamic, EVENTS, False), (static, static_path(EVENTS), True)]]


@pytest.mark.parametrize('cursor', [str(MAX_CURSOR + 1), str(2**128), '-1', 'not-an-integer'])
@pytest.mark.parametrize('existing', [True, False])
def test_http_cursor_invalid_rejected_before_store_without_writes(client, cursor, existing, monkeypatch):
    created, _, _ = create_task(client)
    run_id = created.json()['initial_run']['id'] if existing else 'run_missing'
    before = snapshot(client)
    calls = []
    original = client.app.state.service.store.events
    def observe(*args, **kwargs):
        calls.append((args, kwargs))
        return original(*args, **kwargs)
    monkeypatch.setattr(client.app.state.service.store, 'events', observe)
    result = client.get('/api/v1/runs/' + run_id + '/events', params={'after': cursor})
    assert result.status_code == 422, result.text
    assert result.json()['error']['code'] == 'VALIDATION_ERROR'
    for check in checks(client, EVENTS, 'get', 422):
        check.validate(result.json())
    assert calls == []
    assert snapshot(client) == before


@pytest.mark.parametrize('cursor', [0, 1, MAX_CURSOR - 1, MAX_CURSOR])
def test_http_cursor_valid_range_and_empty_page_are_exact(client, cursor):
    created, _, _ = create_task(client)
    run_id = created.json()['initial_run']['id']
    before = snapshot(client)
    response = client.get('/api/v1/runs/' + run_id + '/events', params={'after': str(cursor)})
    assert response.status_code == 200, response.text
    result = response.json()
    assert all(e['sequence'] > cursor for e in result['items'])
    assert result['next_cursor'] == (result['items'][-1]['sequence'] if result['items'] else cursor)
    if cursor >= MAX_CURSOR - 1:
        assert result == {'items': [], 'next_cursor': cursor}
    for check in checks(client, EVENTS, 'get', 200):
        check.validate(result)
    for check in cursor_checks(client):
        check.validate(cursor)
    assert snapshot(client) == before
    missing = client.get('/api/v1/runs/run_missing/events', params={'after': str(cursor)})
    assert missing.status_code == 404 and missing.json()['error']['code'] == 'NOT_FOUND'
    assert snapshot(client) == before


@pytest.mark.parametrize('cursor', [-1, MAX_CURSOR + 1, 2**128, True, 1.5, None, '1'])
def test_cursor_parameter_contract_rejects_invalid_values(client, cursor):
    for check in cursor_checks(client):
        assert not check.is_valid(cursor), cursor


@pytest.mark.parametrize('cursor', [-1, MAX_CURSOR + 1, 2**128, True, 1.0, 1.5, None, '1'])
def test_store_cursor_guard_is_independent_of_http(client, cursor):
    created, _, _ = create_task(client)
    store = client.app.state.service.store
    before = snapshot(client)
    with pytest.raises(Problem) as caught:
        store.events(created.json()['initial_run']['id'], cursor)
    assert (caught.value.code, caught.value.status) == ('VALIDATION_ERROR', 422)
    assert snapshot(client) == before


def test_maximum_persistable_event_sequence_remains_readable(client):
    created, _, _ = create_task(client)
    run_id = created.json()['initial_run']['id']
    store = client.app.state.service.store
    # Seed a sparse high sequence in an isolated DB, not billions of real events.
    with store.transaction() as db:
        run = store.get('runs', run_id)
        run['latest_sequence'] = MAX_CURSOR - 2
        store.event(db, run, 'test.boundary', {'ordinal': 1})
        store.event(db, run, 'test.boundary', {'ordinal': 2})
    before = snapshot(client)
    response = client.get('/api/v1/runs/' + run_id + '/events', params={'after': str(MAX_CURSOR - 2)})
    assert response.status_code == 200
    result = response.json()
    assert [e['sequence'] for e in result['items']] == [MAX_CURSOR - 1, MAX_CURSOR]
    assert result['next_cursor'] == MAX_CURSOR
    for check in checks(client, EVENTS, 'get', 200):
        check.validate(result)
        for field in ['next_cursor', 'sequence']:
            bad = copy.deepcopy(result)
            if field == 'next_cursor':
                bad[field] = MAX_CURSOR + 1
            else:
                bad['items'][0][field] = MAX_CURSOR + 1
            assert not check.is_valid(bad), field
    run = client.get('/api/v1/runs/' + run_id).json()
    assert run['latest_sequence'] == MAX_CURSOR
    for check in checks(client, '/api/v1/runs/{run_id}', 'get', 200):
        check.validate(run)
        assert not check.is_valid({**run, 'latest_sequence': MAX_CURSOR + 1})
    assert snapshot(client) == before


@pytest.mark.parametrize('path,field', [(EVENTS, 'run_id'), (EVENTS, 'task_id'),
                                     ('/api/v1/runs/{run_id}/artifacts', 'run_id')])
@pytest.mark.parametrize('wrong', ['rts_other', 'teamtask_other', '', 'run_'])
def test_product_reference_format_not_other_domains(client, path, field, wrong):
    created, _, _ = create_task(client)
    run_id = created.json()['initial_run']['id']
    client.app.state.service.execute(run_id)
    result = client.get(path.replace('{run_id}', run_id)).json()
    assert result['items']
    bad = copy.deepcopy(result)
    bad['items'][0][field] = wrong
    for check in checks(client, path, 'get', 200):
        check.validate(result)
        errors = list(check.iter_errors(bad))
        assert any(e.validator == 'pattern' and list(e.absolute_path) == ['items', 0, field] for e in errors), wrong


def test_dynamic_422_binding_is_strict_error_envelope_everywhere(client):
    dynamic, _, registry = documents(client)
    paths = [(p, m) for p, m, _ in JSON_OPERATIONS] + [('/api/local/sample', 'get'), ('/api/v1/artifacts/{artifact_id}/content', 'get')]
    response = client.get('/api/v1/runs/run_missing/events?after=-1')
    assert response.status_code == 422
    seen = set()
    for path, method in paths:
        responses = dynamic['paths'][path][method]['responses']
        if '422' not in responses:
            continue
        seen.add((path, method))
        schema = responses['422']['content']['application/json']['schema']
        assert schema == {'$ref': '#/components/schemas/local_http_error'}, (path, method)
        check = checker(dynamic, schema, registry)
        check.validate(response.json())
        for invalid in [{}, {'detail': []}, {'error': {}}, {**response.json(), 'detail': []}]:
            assert not check.is_valid(invalid), (path, method, invalid)
    assert {(EVENTS, 'get'), ('/api/v1/resources/{resource_id}', 'get'),
            ('/api/v1/tasks/{task_id}', 'get')} <= seen


def test_task_detail_requires_runs_even_if_other_fields_valid(client):
    created, _, _ = create_task(client)
    path = '/api/v1/tasks/{task_id}'
    result = client.get(path.replace('{task_id}', created.json()['task']['id'])).json()
    assert result['runs']
    for check in checks(client, path, 'get', 200):
        check.validate(result)
        check.validate({**result, 'runs': []})
        bad = {k: v for k, v in result.items() if k != 'runs'}
        assert any(e.validator == 'required' and "'runs'" in e.message for e in check.iter_errors(bad))


@pytest.mark.parametrize('invalid', [True, None, 'false', 0])
def test_error_retryable_must_be_literal_false(client, invalid):
    result = client.get('/api/v1/runs/run_missing').json()
    assert result['error']['retryable'] is False
    for check in checks(client, '/api/v1/runs/{run_id}', 'get', 'default'):
        check.validate(result)
        bad = copy.deepcopy(result)
        bad['error']['retryable'] = invalid
        assert any(e.validator == 'const' and list(e.absolute_path) == ['error', 'retryable'] for e in check.iter_errors(bad))


@pytest.mark.parametrize('timestamp,valid', [
    ('2026-10-04T01:02:03Z', True), ('2026-10-04T01:02:03.123456Z', True),
    ('2026-10-04T01:02:03+00:00', True), ('2024-02-29T00:00:00Z', True),
    ('2026-10-04T01:02:03', False), ('2026-10-04T01:02:03+08:00', False),
    ('2026-10-04T01:02:03-05:00', False), ('2026-10-04T01:02:03-00:00', False),
    ('2026-10-04', False), ('2026-10-04 01:02:03Z', False),
    ('2026-02-29T00:00:00Z', False), ('2026-10-04T24:00:00Z', False),
    ('2026-10-04T01:02:03Z\n', False), ('not-a-time', False),
])
def test_utc_checker_has_schema_level_positive_and_negative_vectors(client, timestamp, valid):
    _, _, resource = create_task(client)
    result = resource.json()
    for check in checks(client, '/api/v1/resources', 'post', 201):
        check.validate(result)
        modified = {**result, 'created_at': timestamp}
        if valid:
            check.validate(modified)
        else:
            errors = list(check.iter_errors(modified))
            assert any(e.validator == 'format' and list(e.absolute_path) == ['created_at'] for e in errors), timestamp
