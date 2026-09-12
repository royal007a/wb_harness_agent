import copy
import json
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from backend.analysis import Problem, analyze, digest, parse_csv
from backend.app import create_app
from backend.service import ROOT, local_task, validate
from backend.store import dumps


@pytest.fixture
def app(tmp_path):
    return create_app(tmp_path / 'test.db', run_worker=False)


@pytest.fixture
def client(app):
    with TestClient(app, base_url='http://127.0.0.1') as client:
        yield client


def submit(client, key='test-key', objective='分析数据'):
    resource = client.post('/api/v1/resources?name=data.csv', content=b'name,value\nA,2\nB,4\nC,\n').json()
    body = local_task(resource['id'], objective)
    response = client.post('/api/v1/tasks', json=body, headers={'Idempotency-Key': key})
    assert response.status_code == 202, response.text
    return response.json(), body


def test_complete_contracts_artifacts_and_cursor(client, app):
    data, body = submit(client)
    validate('task', data['task'])
    run_id = data['initial_run']['id']
    app.state.service.execute(run_id)
    run = client.get('/api/v1/runs/' + run_id).json()
    assert run['status'] == 'succeeded', run
    validate('run', run)
    events = client.get(f'/api/v1/runs/{run_id}/events').json()['items']
    assert [e['sequence'] for e in events] == list(range(1, len(events) + 1))
    assert events[-1]['event_type'] == 'run.succeeded'
    for event in events:
        validate('event', event)
    assert client.get(f'/api/v1/runs/{run_id}/events?after={events[-1]["sequence"]}').json()['items'] == []
    artifacts = client.get(f'/api/v1/runs/{run_id}/artifacts').json()['items']
    assert len(artifacts) == 3
    for artifact in artifacts:
        validate('artifact', artifact)
        response = client.get(f'/api/v1/artifacts/{artifact["id"]}/content')
        assert digest(response.content) == artifact['sha256']
        if artifact['name'].endswith('.json'):
            manifest = response.json()
            assert manifest['metrics']['columns'][1]['sum'] == 6
            assert manifest['metrics']['missing_cells'] == 1
            assert manifest['usage']['model_calls'] == 0
    # Terminal states cannot be overwritten by a late cancellation or worker retry.
    assert client.post(f'/api/v1/runs/{run_id}:cancel').json()['status'] == 'succeeded'
    app.state.service.execute(run_id)
    assert len(app.state.service.store.events(run_id)) == len(events)


def test_idempotency_rerun_and_conflict(client, app):
    data, body = submit(client)
    again = client.post('/api/v1/tasks', json=body, headers={'Idempotency-Key': 'test-key'})
    assert again.json() == data
    other = {**body, 'objective': 'different'}
    assert client.post('/api/v1/tasks', json=other, headers={'Idempotency-Key': 'test-key'}).status_code == 409
    task_id = data['task']['id']
    endpoint = f'/api/v1/tasks/{task_id}/runs'
    payload = {'based_on_run_id': data['initial_run']['id']}
    first = client.post(endpoint, json=payload, headers={'Idempotency-Key': 'rerun'})
    second = client.post(endpoint, json=payload, headers={'Idempotency-Key': 'rerun'})
    assert first.status_code == 202
    assert first.json() == second.json()
    assert first.json()['attempt_number'] == 2
    assert client.get('/api/v1/tasks/' + task_id).json()['task'] == data['task']
    second_task, _ = submit(client, key='second')
    assert client.post(endpoint, json={'based_on_run_id': second_task['initial_run']['id']}, headers={'Idempotency-Key': 'bad'}).status_code == 422


def test_concurrent_idempotency(client, app):
    data, body = submit(client)
    with ThreadPoolExecutor(max_workers=8) as pool:
        values = list(pool.map(lambda _: app.state.service.create_task(body, 'concurrent'), range(16)))
    assert len({v['task']['id'] for v in values}) == 1
    assert len(app.state.service.store.listing('tasks')) == 2


@pytest.mark.parametrize('mutation,code', [
    (lambda b: b.update(extra='unknown'), 'VALIDATION_ERROR'),
    (lambda b: b.update(project_id='prj_other'), 'FORBIDDEN'),
    (lambda b: b['engine_policy'].update(engine_id='engine_smolagents_code'), 'ENGINE_UNAVAILABLE'),
    (lambda b: b['engine_policy'].update(required_capabilities=['actions.code']), 'ENGINE_UNAVAILABLE'),
    (lambda b: b['model_policy'].update(vision='doubao-seed-2.1-turbo'), 'MODEL_CAPABILITY_MISMATCH'),
    (lambda b: b['requested_permissions']['allow_tools'].append('shell.exec'), 'FORBIDDEN'),
    (lambda b: b['requested_permissions'].update(allow_tools=['resource.inspect']), 'FORBIDDEN'),
    (lambda b: b['context'].update(variables={'code': 'print(1)'}), 'VALIDATION_ERROR'),
    (lambda b: b['limits'].update(timeout_seconds=0), 'VALIDATION_ERROR'),
    (lambda b: b.update(objective=' '), 'VALIDATION_ERROR'),
])
def test_reject_unsupported_contract(client, mutation, code):
    _, body = submit(client)
    mutation(body)
    response = client.post('/api/v1/tasks', json=body, headers={'Idempotency-Key': 'reject'})
    assert response.status_code in (403, 409, 422), response.text
    assert response.json()['error']['code'] == code


def test_cancel_queued(client, app):
    data, _ = submit(client)
    run_id = data['initial_run']['id']
    first = client.post(f'/api/v1/runs/{run_id}:cancel').json()
    assert first['status'] == 'cancelled'
    assert client.post(f'/api/v1/runs/{run_id}:cancel').json() == first
    app.state.service.execute(run_id)
    assert app.state.service.store.artifact_list(run_id) == []


def test_cancel_running_prevents_publication(client, app, monkeypatch):
    data, _ = submit(client)
    run_id = data['initial_run']['id']
    started, release = threading.Event(), threading.Event()
    from backend import service
    original = service.analyze
    def slow(raw, check):
        started.set()
        assert release.wait(3)
        return original(raw, check)
    monkeypatch.setattr(service, 'analyze', slow)
    worker = threading.Thread(target=app.state.service.execute, args=(run_id,))
    worker.start()
    assert started.wait(3)
    assert client.post(f'/api/v1/runs/{run_id}:cancel').json()['status'] == 'cancelled'
    release.set()
    worker.join(3)
    assert not worker.is_alive()
    assert app.state.service.store.artifact_list(run_id) == []


def test_timeout_and_budget(client, app):
    data, _ = submit(client)
    store = app.state.service.store
    run_id = data['initial_run']['id']
    with store.transaction() as db:
        run = store.get('runs', run_id)
        run['created_at'] = (datetime.now(timezone.utc) - timedelta(seconds=1000)).isoformat()
        db.execute('UPDATE runs SET doc=? WHERE id=?', (dumps(run), run_id))
    app.state.service.execute(run_id)
    assert store.get('runs', run_id)['status'] == 'expired'
    _, body = submit(client, 'budget-source')
    body['limits']['max_turns'] = 1
    run_id = app.state.service.create_task(body, 'budget')['initial_run']['id']
    app.state.service.execute(run_id)
    assert store.get('runs', run_id)['exit_reason'] == 'BUDGET_EXCEEDED'


def test_recover_persistence_and_single_owner(tmp_path):
    target = tmp_path / 'persist.db'
    with TestClient(create_app(target, False), base_url='http://127.0.0.1') as client:
        data, _ = submit(client)
        service = client.app.state.service
        with service.store.transaction() as db:
            run = service.store.get('runs', data['initial_run']['id'])
            run['status'] = 'running'
            service.store.event(db, run, 'run.started')
        with pytest.raises(RuntimeError, match='already owns'):
            with TestClient(create_app(target, False)):
                pass
    with TestClient(create_app(target, True), base_url='http://127.0.0.1') as client:
        run = client.get('/api/v1/runs/' + data['initial_run']['id']).json()
        assert run['status'] == 'failed'
        assert run['exit_reason'] == 'SERVER_RESTARTED'
        assert client.get('/api/v1/tasks/' + data['task']['id']).json()['task'] == data['task']


def test_real_worker(client, tmp_path):
    with TestClient(create_app(tmp_path / 'worker.db'), base_url='http://127.0.0.1') as running:
        data, _ = submit(running)
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            run = running.get('/api/v1/runs/' + data['initial_run']['id']).json()
            if run['status'] == 'succeeded':
                break
            time.sleep(.05)
        assert run['status'] == 'succeeded'


@pytest.mark.parametrize('raw', [b'', b'a,a\n1,2\n', b'a,b\n1\n', b'a\n', b'\x00foo', b'a\n"bad', b'a'* (2*1024*1024+1)])
def test_bad_csv_rejected(client, raw):
    response = client.post('/api/v1/resources?name=data.csv', content=raw)
    assert response.status_code in (400, 413), response.text


def test_encoding_mixed_missing_and_injection(client, app):
    raw = '字段,数值\n甲,3\n乙,\n丙,9\n'.encode('gb18030')
    result = analyze(raw)
    assert result['encoding'] == 'gb18030'
    assert result['columns'][1]['mean'] == 6
    assert analyze(b'x\nNaN\nInfinity\n')['columns'][0]['type'] == 'text'
    assert analyze(b'x\n1\noops\n')['columns'][0]['type'] == 'text'
    evil = b'<script>alert(1)</script>,value\n=RUN(),2\n'
    resource = client.post('/api/v1/resources?name=evil.csv', content=evil).json()
    run_id = app.state.service.create_task(local_task(resource['id'], '<img src=x onerror=alert(1)>'), 'evil')['initial_run']['id']
    app.state.service.execute(run_id)
    for a in app.state.service.store.artifact_list(run_id):
        if a['media_type'] in ('image/svg+xml', 'text/markdown'):
            text = client.get('/api/v1/artifacts/' + a['id'] + '/content').text
            assert '<script>' not in text
            assert '<img src=x' not in text


def test_http_boundaries_and_unknown_resource(client):
    assert client.get('/api/v1/tasks', headers={'Host': 'evil.example'}).status_code == 403
    assert client.get('/api/v1/tasks', headers={'Origin': 'https://evil.example'}).status_code == 403
    assert client.get('/api/v1/tasks', headers={'Sec-Fetch-Site': 'cross-site'}).status_code == 403
    assert client.post('/api/local/tasks', content='{}').status_code == 415
    assert client.post('/api/local/tasks', content='{oops', headers={'Content-Type': 'application/json'}).status_code == 422
    assert client.get('/api/v1/runs/run_missing').status_code == 404
    assert client.post('/api/v1/resources?name=../secret.csv', content=b'x\n1').status_code == 400
    assert client.get('/static/../backend/store.py').status_code == 404
    assert client.get('/').status_code == 200
    assert client.get('/static/app.js').status_code == 200
    assert "frame-ancestors 'none'" in client.get('/').headers['content-security-policy']
    assert client.get('/docs').status_code == 200
    schema = client.get('/openapi.json').json()
    def refs(value):
        if isinstance(value, dict):
            for key, child in value.items():
                if key == '$ref' and child.startswith('#/'):
                    resolved = schema
                    for segment in child[2:].split('/'):
                        resolved = resolved[segment]
                else:
                    refs(child)
        elif isinstance(value, list):
            for child in value:
                refs(child)
    refs(schema)


def test_resource_integrity_failure(client, app):
    data, body = submit(client)
    store = app.state.service.store
    with store.transaction() as db:
        db.execute('UPDATE resources SET raw=? WHERE id=?', (b'x\n999', body['context']['resource_ids'][0]))
    run_id = data['initial_run']['id']
    app.state.service.execute(run_id)
    assert store.get('runs', run_id)['exit_reason'] == 'RESOURCE_INTEGRITY_ERROR'
    assert store.artifact_list(run_id) == []


def test_publication_failure_rolls_back_artifacts(client, app, monkeypatch):
    data, _ = submit(client)
    store = app.state.service.store
    original = store.event
    def fail(db, run, kind, *args):
        if kind == 'artifact.validation.completed':
            raise RuntimeError('injected publication failure')
        return original(db, run, kind, *args)
    monkeypatch.setattr(store, 'event', fail)
    run_id = data['initial_run']['id']
    app.state.service.execute(run_id)
    assert store.get('runs', run_id)['status'] == 'failed'
    assert store.artifact_list(run_id) == []
    assert not any(e['event_type'] == 'artifact.published' for e in store.events(run_id))


def test_nonfinite_json_and_input_bounds(client):
    response = client.post('/api/local/tasks', content='{"resource_id":"res_a","objective":NaN}', headers={'Content-Type': 'application/json'})
    assert response.status_code == 422
    assert client.get('/api/v1/runs/run_unknown/events?after=abc').json()['error']['code'] == 'VALIDATION_ERROR'
    with pytest.raises(Problem):
        parse_csv(b'a\n' + b'1\n' * 20001)
    with pytest.raises(Problem):
        parse_csv((','.join(str(i) for i in range(101)) + '\n').encode())


def test_queued_restart_resumes(tmp_path):
    db = tmp_path / 'queued.db'
    with TestClient(create_app(db, False), base_url='http://127.0.0.1') as client:
        data, _ = submit(client)
    with TestClient(create_app(db), base_url='http://127.0.0.1') as client:
        run_id = data['initial_run']['id']
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            run = client.get('/api/v1/runs/' + run_id).json()
            if run['status'] == 'succeeded':
                break
            time.sleep(.05)
        assert run['status'] == 'succeeded'
        assert len(client.get('/api/v1/tasks/' + data['task']['id'] + '/artifacts').json()['items']) == 3
