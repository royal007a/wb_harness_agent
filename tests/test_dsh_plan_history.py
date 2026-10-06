"""HA-0087: actual Store/HTTP projection; synthetic bridge, never SDK or network."""
import copy
import json
import threading

import pytest
from fastapi.testclient import TestClient

from backend.app import create_app
from backend.dsh_plan import project


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv('HARNESS_DSH_LOCAL', 'enabled')
    monkeypatch.setenv('HARNESS_DSH_RUN_ROOT', str(tmp_path.resolve() / 'runs'))
    monkeypatch.delenv('HARNESS_DSH_REAL_ENABLED', raising=False)
    with TestClient(create_app(tmp_path / 'test.db', run_worker=False), base_url='http://localhost',
                    raise_server_exceptions=False) as value:
        yield value


def create(client, key='history'):
    response = client.post('/api/local/dsh/runs', json={
        'objective': '核对付款条件', 'document': '甲方验收后30天付款。',
        'public_data_confirmed': True, 'mode': 'integration_probe', 'template': 'payment_terms',
    }, headers={'Idempotency-Key': key})
    assert response.status_code == 201
    return response.json()['initial_run']['id']


def filler(store, db, run, until):
    while run['latest_sequence'] < until:
        store.event(db, run, 'dsh.observation', {'type': 'observation', 'sha256': 'a' * 64, 'bytes': 1})


def initial_plan():
    return project({'payment': ['clause-1'], 'exception': []}, set(), {})


def snapshot(store):
    return '\n'.join(store.db.iterdump()), store.db.total_changes


def readonly_detail(client, ident, monkeypatch):
    rt = client.app.state.service.dsh
    def forbidden(*args, **kwargs):
        pytest.fail('reading history must not execute or resolve credentials')
    monkeypatch.setattr(rt, 'execute', forbidden)
    monkeypatch.setattr(rt.adapter, 'run', forbidden)
    monkeypatch.setattr(rt, 'send_probe', forbidden)
    monkeypatch.setattr(rt, 'send_real', forbidden)
    monkeypatch.setattr(rt.credentials, 'resolve', forbidden)
    before = snapshot(rt.store)
    response = client.get('/api/local/dsh/runs/' + ident)
    assert response.status_code == 200, response.text
    assert snapshot(rt.store) == before
    return response.json()


@pytest.mark.parametrize('sequence', [499, 500, 501, 999, 1000, 1001])
def test_step_update_on_each_page_boundary(client, monkeypatch, sequence):
    ident = create(client)
    store = client.app.state.service.store
    with store.transaction() as db:
        run = store.get('runs', ident)
        store.event(db, run, 'dsh.plan.created', initial_plan())
        filler(store, db, run, sequence - 1)
        store.event(db, run, 'dsh.plan.step', {'steps': [
            {'step_id': 'S1', 'status': 'done', 'evidence_ids': ['clause-1'], 'missing_ids': [], 'error_codes': []},
            {'step_id': 'S3', 'status': 'blocked', 'error_codes': ['CLAIM_VALUE_NOT_IN_QUOTE']},
        ]})
    detail = readonly_detail(client, ident, monkeypatch)
    steps = {s['step_id']: s for s in detail['plan']['steps']}
    assert steps['S1']['status'] == 'done'
    assert steps['S1']['evidence_ids'] == ['clause-1'] and steps['S1']['missing_ids'] == []
    assert steps['S3']['status'] == 'blocked'
    assert steps['S3']['error_codes'] == ['CLAIM_VALUE_NOT_IN_QUOTE']
    # The public API still pages instead of exposing an unbounded event list.
    page = client.get('/api/local/dsh/runs/' + ident + '/events').json()
    assert len(page['items']) == min(sequence, 500)
    assert page['next_cursor'] == min(sequence, 500)


def test_plan_created_after_first_page_and_sparse_sequences(client, monkeypatch):
    ident = create(client)
    store = client.app.state.service.store
    with store.transaction() as db:
        run = store.get('runs', ident)
        filler(store, db, run, 500)
        # Sparse sequence is a read-path probe, not a production event writer claim.
        run['latest_sequence'] = 9000
        store.event(db, run, 'dsh.plan.created', initial_plan())
        store.event(db, run, 'dsh.plan.step', {'steps': [{'step_id': 'S1', 'status': 'partial',
            'evidence_ids': ['clause-1'], 'missing_ids': ['clause-2'], 'error_codes': []}]})
    detail = readonly_detail(client, ident, monkeypatch)
    assert detail['plan'] is not None
    assert detail['plan']['steps'][0]['status'] == 'partial'
    assert detail['plan']['steps'][0]['missing_ids'] == ['clause-2']


def test_internal_reader_uses_actual_cursor_and_accepts_short_pages(client, monkeypatch):
    ident = create(client)
    rt = client.app.state.service.dsh
    with rt.store.transaction() as db:
        run = rt.store.get('runs', ident)
        rt.store.event(db, run, 'dsh.plan.created', initial_plan())
        filler(rt.store, db, run, 3)
        run['latest_sequence'] = 9000
        rt.store.event(db, run, 'dsh.plan.step', {'steps': [{'step_id': 'S3', 'status': 'blocked'}]})
    original, cursors = rt.store.events, []
    def short_pages(run_id, after=0):
        cursors.append(after)
        assert len(cursors) <= 4, 'cursor failed to advance by observed sequence'
        return original(run_id, after)[:2]
    monkeypatch.setattr(rt.store, 'events', short_pages)
    detail = readonly_detail(client, ident, monkeypatch)
    assert detail['plan']['steps'][2]['status'] == 'blocked'
    assert cursors == [0, 2, 9001]


def test_pages_share_lock_with_run_snapshot(client, monkeypatch):
    ident = create(client)
    rt = client.app.state.service.dsh
    with rt.store.transaction() as db:
        run = rt.store.get('runs', ident)
        rt.store.event(db, run, 'dsh.plan.created', initial_plan())
        filler(rt.store, db, run, 501)
    go, attempting, committed = threading.Event(), threading.Event(), threading.Event()
    errors = []
    def writer():
        try:
            assert go.wait(5)
            attempting.set()
            with rt.store.transaction() as db:
                value = rt.store.get('runs', ident)
                rt.store.event(db, value, 'dsh.plan.step', {'steps': [{'step_id': 'S3', 'status': 'blocked'}]})
            committed.set()
        except BaseException as exc:
            errors.append(exc)
    original = rt.store.events
    pages = []
    def observed(run_id, after=0):
        # An unlocked iterator is insufficient even when the last step looks right.
        assert rt.store.lock._is_owned(), 'page read escaped the detail snapshot lock'
        if not pages:
            go.set()
            assert attempting.wait(5)
        assert not committed.is_set()
        pages.append(after)
        return original(run_id, after)
    thread = threading.Thread(target=writer)
    monkeypatch.setattr(rt.store, 'events', observed)
    thread.start()
    try:
        result = rt.detail(ident)
    finally:
        go.set()
        thread.join(5)
        monkeypatch.setattr(rt.store, 'events', original)
    assert not thread.is_alive() and not errors
    assert committed.is_set() and pages == [0, 500, 501]
    assert result['run']['latest_sequence'] == 501
    assert result['plan']['steps'][2]['status'] == 'pending'
    assert rt.detail(ident)['plan']['steps'][2]['status'] == 'blocked'


def test_rejected_late_submission_overrides_old_pass_and_cancel_preserves_it(client, monkeypatch):
    ident = create(client)
    rt = client.app.state.service.dsh
    with rt.store.transaction() as db:
        run = rt.store.get('runs', ident)
        rt.store.event(db, run, 'dsh.plan.created', initial_plan())
        rt.store.event(db, run, 'dsh.plan.step', {'steps': [
            {'step_id': 'S3', 'status': 'done', 'error_codes': []}, {'step_id': 'S4', 'status': 'ready'}]})
        filler(rt.store, db, run, 1000)
        rt.store.event(db, run, 'dsh.plan.step', {'steps': [
            {'step_id': 'S3', 'status': 'blocked', 'error_codes': ['CLAIM_VALUE_NOT_IN_QUOTE']},
            {'step_id': 'S4', 'status': 'pending'}]})
    rt.cancel(ident)
    detail = readonly_detail(client, ident, monkeypatch)
    assert detail['run']['status'] == 'cancelled' and detail['artifacts'] == []
    assert detail['plan']['steps'][2]['status'] == 'blocked'
    assert detail['plan']['steps'][3]['status'] == 'pending'


def test_free_legacy_run_without_plan_stays_null(client, monkeypatch):
    ident = create(client)
    rt = client.app.state.service.dsh
    with rt.store.transaction() as db:
        run = rt.store.get('runs', ident)
        filler(rt.store, db, run, 1001)
    assert readonly_detail(client, ident, monkeypatch)['plan'] is None


def test_page_read_failure_does_not_return_partial_plan(client, monkeypatch):
    ident = create(client)
    rt = client.app.state.service.dsh
    with rt.store.transaction() as db:
        run = rt.store.get('runs', ident)
        rt.store.event(db, run, 'dsh.plan.created', initial_plan())
        filler(rt.store, db, run, 501)
    original = rt.store.events
    def events(run_id, after=0):
        if after:
            raise RuntimeError('SYNTH_HISTORY_SECRET')
        return original(run_id, after)
    monkeypatch.setattr(rt.store, 'events', events)
    before = snapshot(rt.store)
    response = client.get('/api/local/dsh/runs/' + ident)
    assert response.status_code == 500
    assert 'plan' not in response.json() and 'SYNTH_HISTORY_SECRET' not in response.text
    assert snapshot(rt.store) == before


def synthetic_bridge(prompt, root, model, model_call, tool_call, emit, check, **kwargs):
    messages = [{'role': 'user', 'content': [{'type': 'text', 'text': prompt}]}]
    for _ in range(600):
        emit({'type': 'observation', 'sha256': 'a' * 64, 'bytes': 1})
    ticket = 'm_1'
    for turn in range(8):
        response = model_call({'crossing_id': ticket, 'request': {
            'model': model, 'purpose': 'primary', 'messages': messages,
            'tools': [{'name': name, 'parameters': {'type': 'object'}} for name in kwargs['tools']]}})
        value = response['value']
        if not value['tool_calls']:
            return {'type': 'result', 'text': value['text'], 'session_sha256': 'a' * 64,
                    'turn_count': turn + 1, 'runtime': 'deepseek-harness@0.2.1-alpha.1'}
        calls = value['tool_calls']
        messages.append({'role': 'assistant', 'content': [dict(type='tool-call', **c) for c in calls]})
        for call in calls:
            result = tool_call({'crossing_id': call['id'], 'request': {
                'name': call['name'], 'arguments': json.loads(call['arguments'])}})
            messages.append({'role': 'tool', 'toolCallId': call['id'],
                             'content': [{'type': 'text', 'text': result['text']}]})
        ticket = response['next_model_crossing']
    pytest.fail('synthetic bridge did not finish')


def test_actual_publication_after_600_observations_and_reopen(tmp_path, monkeypatch):
    monkeypatch.setenv('HARNESS_DSH_LOCAL', 'enabled')
    monkeypatch.setenv('HARNESS_DSH_RUN_ROOT', str(tmp_path.resolve() / 'runs'))
    monkeypatch.delenv('HARNESS_DSH_REAL_ENABLED', raising=False)
    with TestClient(create_app(tmp_path / 'test.db', run_worker=False), base_url='http://localhost') as first:
        ident = create(first)
        rt = first.app.state.service.dsh
        monkeypatch.setattr(rt.adapter, 'run', synthetic_bridge)
        rt.execute(ident)
        detail = readonly_detail(first, ident, monkeypatch)
        assert detail['run']['status'] == 'succeeded', detail['run']['exit_reason']
        assert detail['budget']['calls'] == 3 and detail['run']['latest_sequence'] > 600
        assert [s['status'] for s in detail['plan']['steps']] == ['done', 'not_applicable', 'done', 'done']
        assert detail['plan']['steps'][0]['evidence_ids'] == ['clause-1']
        expected = copy.deepcopy(detail)
    # Lifespan closes the original connection and ownership lease before reopen.
    with TestClient(create_app(tmp_path / 'test.db', run_worker=False), base_url='http://localhost') as second:
        assert readonly_detail(second, ident, monkeypatch) == expected
