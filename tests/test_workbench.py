import copy
import json
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone

import pytest
import yaml
from fastapi.testclient import TestClient

from backend.analysis import Problem, analyze, digest, parse_csv
from backend.app import create_app
import backend.service as service_module
from backend.service import ROOT, checkpoint_document_digest, local_task, validate
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


def fail_after_checkpoint(client, app, monkeypatch):
    """Create a terminal source Run with a persisted checkpoint but no artifacts."""
    data, _ = submit(client, key='checkpoint-source')
    source_id = data['initial_run']['id']
    original_artifacts = service_module.artifacts

    def injected_failure(*args, **kwargs):
        raise Problem('INJECTED_POST_CHECKPOINT', '测试：在 Checkpoint 之后停止发布。')

    monkeypatch.setattr(service_module, 'artifacts', injected_failure)
    app.state.service.execute(source_id)
    monkeypatch.setattr(service_module, 'artifacts', original_artifacts)
    source = app.state.service.store.get('runs', source_id)
    checkpoint = app.state.service.store.latest_checkpoint(source_id)
    assert source['status'] == 'failed'
    assert source['exit_reason'] == 'ARTIFACT_PUBLICATION_FAILED'
    assert checkpoint is not None
    assert app.state.service.store.artifact_list(source_id) == []
    gaps = app.state.service.store.gaps_for_run(source_id)
    assert len(gaps) == 1
    assert gaps[0]['status'] == 'open'
    assert gaps[0]['required_by'] == 'node_publish'
    assert gaps[0]['resolvable_action_ids'] == ['artifact.publish']
    return data, source, checkpoint


def local_replan(client, source_id, key='replan-propose'):
    response = client.post(f'/api/v1/runs/{source_id}/replans', json={}, headers={'Idempotency-Key': key})
    assert response.status_code == 201, response.text
    return response.json()


def test_static_openapi_includes_the_runtime_replan_tcc_contract(app):
    static = yaml.safe_load((ROOT / 'specs/v1/openapi.yaml').read_text())
    static_paths = static['paths']
    runtime_paths = app.openapi()['paths']
    pairs = {
        '/local/runs/{runId}/restore': '/api/local/runs/{run_id}/restore',
        '/local/runs/{runId}:restore': '/api/local/runs/{run_id}:restore',
        '/runs/{runId}/replans': '/api/v1/runs/{run_id}/replans',
        '/replans/{replanId}': '/api/v1/replans/{replan_id}',
        '/replans/{replanId}:try': '/api/v1/replans/{replan_id}:try',
        '/replans/{replanId}:confirm': '/api/v1/replans/{replan_id}:confirm',
        '/replans/{replanId}:cancel': '/api/v1/replans/{replan_id}:cancel',
    }
    for static_path, runtime_path in pairs.items():
        assert static_path in static_paths and runtime_path in runtime_paths
    runtime_schema = app.openapi()
    assert runtime_schema['paths']['/api/v1/runs/{run_id}/replans']['get']['responses']['200']['content']['application/json']['schema'] == {
        '$ref': '#/components/schemas/ReplanList'}
    assert runtime_schema['paths']['/api/v1/replans/{replan_id}']['get']['responses']['200']['content']['application/json']['schema'] == {
        '$ref': '#/components/schemas/ReplanDetail'}
    assert runtime_schema['components']['schemas']['ReplanDetail']['required'] == ['attempt', 'candidate_plan', 'gaps']
    assert runtime_schema['components']['schemas']['ReplanDetail']['properties']['gaps']['items'] == {
        '$ref': '#/components/schemas/gap'}
    for static_path in ('/runs/{runId}/replans', '/replans/{replanId}:try',
                        '/replans/{replanId}:confirm', '/replans/{replanId}:cancel'):
        operation = static_paths[static_path]['post']
        assert any(p.get('$ref') == '#/components/parameters/IdempotencyKey'
                   for p in operation['parameters'])
        assert operation['requestBody']['content']['application/json']['schema']['$ref'] == '#/components/schemas/EmptyObject'
    restore = static_paths['/local/runs/{runId}:restore']['post']
    assert static_paths['/local/runs/{runId}:restore']['servers'] == [{'url': '/api'}]
    assert any(p.get('$ref') == '#/components/parameters/IdempotencyKey' for p in restore['parameters'])
    assert restore['requestBody']['content']['application/json']['schema']['$ref'].endswith('#/$defs/restore_request')


def update_checkpoint(store, checkpoint, mutate):
    changed = copy.deepcopy(checkpoint)
    mutate(changed)
    changed['sha256'] = checkpoint_document_digest(changed)
    with store.transaction() as db:
        db.execute('UPDATE checkpoints SET doc=? WHERE id=?', (dumps(changed), changed['id']))
    return changed


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


def test_checkpoint_restore_creates_bound_new_run_and_keeps_source_terminal(client, app, monkeypatch):
    data, source, checkpoint = fail_after_checkpoint(client, app, monkeypatch)
    source_id = source['id']
    status = client.get(f'/api/local/runs/{source_id}/restore').json()
    assert status == {'eligible': True, 'checkpoint_id': checkpoint['id'], 'reason_code': None}

    endpoint = f'/api/local/runs/{source_id}:restore'
    headers = {'Idempotency-Key': 'restore-source'}
    first = client.post(endpoint, json={}, headers=headers)
    second = client.post(endpoint, json={}, headers=headers)
    assert first.status_code == second.status_code == 202
    assert first.json() == second.json()
    equivalent = client.post(endpoint, json={}, headers={'Idempotency-Key': 'restore-source-different-key'})
    assert equivalent.status_code == 202
    assert equivalent.json() == first.json()
    restored_id = first.json()['run_id']
    restored = app.state.service.store.get('runs', restored_id)
    assert restored['task_id'] == data['task']['id']
    assert restored['based_on_run_id'] == source_id
    assert restored['restored_from_checkpoint_id'] == checkpoint['id']
    assert restored['effective_limits'] == checkpoint['remaining_limits']
    assert restored['consumed_turns'] == 0
    assert app.state.service.store.get('runs', source_id)['status'] == 'failed'

    app.state.service.execute(restored_id)
    restored = app.state.service.store.get('runs', restored_id)
    assert restored['status'] == 'succeeded'
    assert restored['consumed_turns'] == 2
    events = app.state.service.store.events(restored_id)
    assert [event['event_type'] for event in events[:3]] == ['run.queued', 'run.started', 'checkpoint.restored']
    assert not any(event['data'].get('tool') == 'resource.inspect' for event in events)
    manifest = next(a for a in app.state.service.store.artifact_list(restored_id) if a['name'] == 'analysis-manifest.json')
    body = client.get(f'/api/v1/artifacts/{manifest["id"]}/content').json()
    saved_state = json.loads(app.state.service.store.checkpoint_state(checkpoint['id']))
    assert body['metrics'] == saved_state['metrics']
    assert body['usage'] == {'model_calls': 0, 'cost_minor': 0}
    assert app.state.service.store.gaps_for_run(source_id)[0]['status'] == 'resolved'
    assert any(event['event_type'] == 'gap.resolved' for event in events)
    assert client.get(f'/api/local/runs/{source_id}/restore').json()['eligible'] is True


def test_deterministic_replan_runs_explicit_try_confirm_and_bound_recovery(client, app, monkeypatch):
    data, source, checkpoint = fail_after_checkpoint(client, app, monkeypatch)
    source_id = source['id']
    before = len(app.state.service.store.listing('runs'))
    proposed = local_replan(client, source_id)
    assert proposed['status'] == 'proposed'
    assert proposed['checkpoint_id'] == checkpoint['id']
    assert len(app.state.service.store.listing('runs')) == before
    assert local_replan(client, source_id, 'replan-propose-repeat') == proposed
    detail = client.get('/api/v1/replans/' + proposed['replan_id'])
    assert detail.status_code == 200
    assert app.state.service.store.get('runs', source_id)['plan_revision_id'] == detail.json()['attempt']['origin_plan_revision_id']
    assert detail.json()['gaps'][0]['status'] == 'open'
    assert [node['action_id'] for node in detail.json()['candidate_plan']['nodes']] == [
        'checkpoint.verify', 'artifact.publish', 'run.final_answer']
    assert detail.json()['attempt']['root_cause_evidence_ids']

    tried = client.post('/api/v1/replans/' + proposed['replan_id'] + ':try', json={},
                        headers={'Idempotency-Key': 'replan-try'})
    assert tried.status_code == 200, tried.text
    assert tried.json()['status'] == 'awaiting_confirmation'
    assert tried.json()['try_result_digest'] and tried.json()['confirmation_binding_digest']
    assert len(app.state.service.store.listing('runs')) == before

    confirmed = client.post('/api/v1/replans/' + proposed['replan_id'] + ':confirm', json={},
                            headers={'Idempotency-Key': 'replan-confirm'})
    assert confirmed.status_code == 202, confirmed.text
    restored_id = confirmed.json()['run_id']
    assert confirmed.json()['status'] == 'confirmed'
    repeat = client.post('/api/v1/replans/' + proposed['replan_id'] + ':confirm', json={},
                         headers={'Idempotency-Key': 'replan-confirm-repeat'})
    assert repeat.status_code == 202 and repeat.json() == confirmed.json()
    restored = app.state.service.store.get('runs', restored_id)
    assert restored['task_id'] == data['task']['id']
    assert restored['based_on_run_id'] == source_id
    assert restored['restored_from_checkpoint_id'] == checkpoint['id']
    assert restored['plan_revision_id'] == proposed['candidate_plan_revision_id']
    assert restored['replan_attempt_id'] == proposed['replan_id']
    assert app.state.service.store.get('runs', source_id)['status'] == 'failed'

    app.state.service.execute(restored_id)
    restored = app.state.service.store.get('runs', restored_id)
    assert restored['status'] == 'succeeded'
    assert restored['consumed_turns'] == 2
    kinds = [event['event_type'] for event in app.state.service.store.events(restored_id)]
    assert kinds[:5] == ['run.queued', 'run.started', 'checkpoint.restored', 'checkpoint.verified',
                         'plan.revision.activated']
    assert 'resource.inspect' not in [event['data'].get('tool') for event in app.state.service.store.events(restored_id)]
    assert 'gap.resolved' in kinds
    assert client.get('/api/v1/replans/' + proposed['replan_id']).json()['gaps'][0]['status'] == 'resolved'
    direct = client.post(f'/api/local/runs/{source_id}:restore', json={}, headers={'Idempotency-Key': 'direct-after-confirm'})
    assert direct.status_code == 202 and direct.json()['run_id'] == restored_id
    blocked = client.post(f'/api/v1/runs/{source_id}/replans', json={},
                          headers={'Idempotency-Key': 'replan-after-materialized'})
    assert blocked.status_code == 409 and blocked.json()['error']['code'] == 'REPLAN_ALREADY_MATERIALIZED'


def test_deterministic_replan_cancel_is_side_effect_free_and_retryable(client, app, monkeypatch):
    _data, source, _checkpoint = fail_after_checkpoint(client, app, monkeypatch)
    before = len(app.state.service.store.listing('runs'))
    proposed = local_replan(client, source['id'])
    tried = client.post('/api/v1/replans/' + proposed['replan_id'] + ':try', json={},
                        headers={'Idempotency-Key': 'cancel-try'})
    assert tried.json()['status'] == 'awaiting_confirmation'
    cancelled = client.post('/api/v1/replans/' + proposed['replan_id'] + ':cancel', json={},
                            headers={'Idempotency-Key': 'cancel'})
    assert cancelled.status_code == 200 and cancelled.json()['status'] == 'cancelled'
    assert len(app.state.service.store.listing('runs')) == before
    assert app.state.service.store.gaps_for_run(source['id'])[0]['status'] == 'open'
    assert client.post('/api/v1/replans/' + proposed['replan_id'] + ':confirm', json={},
                       headers={'Idempotency-Key': 'cancelled-confirm'}).status_code == 409
    fresh = local_replan(client, source['id'], 'propose-after-cancel')
    assert fresh['replan_id'] != proposed['replan_id'] and fresh['status'] == 'proposed'


def test_deterministic_replan_rejects_caller_input_and_keeps_try_cancel_side_effect_free(client, app, monkeypatch):
    data, source, _checkpoint = fail_after_checkpoint(client, app, monkeypatch)
    endpoint = f'/api/v1/runs/{source["id"]}/replans'
    denied = client.post(endpoint, json={'plan': {'node': 'caller_controlled'}},
                         headers={'Idempotency-Key': 'caller-plan'})
    assert denied.status_code == 422
    assert app.state.service.store.replan_attempts(source['id']) == []

    proposed = local_replan(client, source['id'])
    adapter = app.state.service.adapters['engine_mock_analytics']
    calls = []
    monkeypatch.setattr(adapter, 'restore_run', lambda *args: calls.append('restore'))
    invalid_try = client.post('/api/v1/replans/' + proposed['replan_id'] + ':try', json={'resource_id': 'res_override'},
                              headers={'Idempotency-Key': 'caller-try'})
    assert invalid_try.status_code == 422
    tried = client.post('/api/v1/replans/' + proposed['replan_id'] + ':try', json={},
                        headers={'Idempotency-Key': 'empty-try'})
    assert tried.json()['status'] == 'awaiting_confirmation'
    invalid_cancel = client.post('/api/v1/replans/' + proposed['replan_id'] + ':cancel', json={'goal': 'override'},
                                 headers={'Idempotency-Key': 'caller-cancel'})
    assert invalid_cancel.status_code == 422
    assert calls == []
    detail = client.get('/api/v1/replans/' + proposed['replan_id']).json()
    exposed = json.dumps(detail, ensure_ascii=False)
    assert data['task']['objective'] not in exposed
    assert 'name,value' not in exposed
    cancelled = client.post('/api/v1/replans/' + proposed['replan_id'] + ':cancel', json={},
                            headers={'Idempotency-Key': 'empty-cancel'})
    assert cancelled.json()['status'] == 'cancelled'
    assert calls == []


def test_deterministic_replan_confirm_expires_on_post_try_binding_drift(client, app, monkeypatch):
    _data, source, checkpoint = fail_after_checkpoint(client, app, monkeypatch)
    proposed = local_replan(client, source['id'])
    assert client.post('/api/v1/replans/' + proposed['replan_id'] + ':try', json={},
                       headers={'Idempotency-Key': 'drift-try'}).json()['status'] == 'awaiting_confirmation'
    def mutate(doc):
        doc['bindings']['resource_sha256'] = 'b' * 64
        doc['compatibility_digest'] = digest(dumps(doc['bindings']).encode())
    update_checkpoint(app.state.service.store, checkpoint, mutate)
    before = len(app.state.service.store.listing('runs'))
    stale = client.post('/api/v1/replans/' + proposed['replan_id'] + ':confirm', json={},
                        headers={'Idempotency-Key': 'drift-confirm'})
    assert stale.status_code == 409 and stale.json()['error']['code'] == 'REPLAN_CONFIRMATION_STALE'
    assert len(app.state.service.store.listing('runs')) == before
    assert client.get('/api/v1/replans/' + proposed['replan_id']).json()['attempt']['status'] == 'expired'
    assert app.state.service.store.gaps_for_run(source['id'])[0]['status'] == 'open'


def test_deterministic_replan_does_not_resolve_gap_when_recovery_artifact_publish_fails(client, app, monkeypatch):
    _data, source, _checkpoint = fail_after_checkpoint(client, app, monkeypatch)
    proposed = local_replan(client, source['id'])
    assert client.post('/api/v1/replans/' + proposed['replan_id'] + ':try', json={},
                       headers={'Idempotency-Key': 'recovery-fail-try'}).json()['status'] == 'awaiting_confirmation'
    confirmed = client.post('/api/v1/replans/' + proposed['replan_id'] + ':confirm', json={},
                            headers={'Idempotency-Key': 'recovery-fail-confirm'})
    original_artifacts = service_module.artifacts
    monkeypatch.setattr(service_module, 'artifacts', lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError('publish fail')))
    app.state.service.execute(confirmed.json()['run_id'])
    monkeypatch.setattr(service_module, 'artifacts', original_artifacts)
    restored = app.state.service.store.get('runs', confirmed.json()['run_id'])
    assert restored['status'] == 'failed' and restored['exit_reason'] == 'ARTIFACT_PUBLICATION_FAILED'
    assert app.state.service.store.gaps_for_run(source['id'])[0]['status'] == 'open'
    assert not any(event['event_type'] == 'gap.resolved'
                   for event in app.state.service.store.events(restored['id']))


def test_deterministic_replan_confirm_cas_allows_one_run_under_concurrency(client, app, monkeypatch):
    _data, source, checkpoint = fail_after_checkpoint(client, app, monkeypatch)
    proposed = local_replan(client, source['id'])
    assert client.post('/api/v1/replans/' + proposed['replan_id'] + ':try', json={},
                       headers={'Idempotency-Key': 'cas-try'}).json()['status'] == 'awaiting_confirmation'
    service = app.state.service
    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(
            lambda number: service.confirm_replan(proposed['replan_id'], {}, 'cas-confirm-' + str(number)),
            range(8),
        ))
    assert {result['status'] for result in results} == {'confirmed'}
    assert len({result['run_id'] for result in results}) == 1
    restored = next(run for run in service.store.listing('runs')
                    if run.get('restored_from_checkpoint_id') == checkpoint['id'])
    assert restored['id'] == results[0]['run_id']


def test_deterministic_replan_try_survives_restart_before_confirm(tmp_path, monkeypatch):
    target = tmp_path / 'replan-restart.db'
    with TestClient(create_app(target, False), base_url='http://127.0.0.1') as client:
        _data, source, _checkpoint = fail_after_checkpoint(client, client.app, monkeypatch)
        proposed = local_replan(client, source['id'])
        tried = client.post('/api/v1/replans/' + proposed['replan_id'] + ':try', json={},
                            headers={'Idempotency-Key': 'restart-try'})
        assert tried.json()['status'] == 'awaiting_confirmation'
    with TestClient(create_app(target, False), base_url='http://127.0.0.1') as client:
        detail = client.get('/api/v1/replans/' + proposed['replan_id']).json()
        assert detail['attempt']['status'] == 'awaiting_confirmation'
        confirmed = client.post('/api/v1/replans/' + proposed['replan_id'] + ':confirm', json={},
                                headers={'Idempotency-Key': 'restart-confirm'})
        assert confirmed.status_code == 202 and confirmed.json()['status'] == 'confirmed'
        client.app.state.service.execute(confirmed.json()['run_id'])
        assert client.get('/api/v1/runs/' + confirmed.json()['run_id']).json()['status'] == 'succeeded'


@pytest.mark.parametrize('mutation,code', [
    ('root_cause', 'REPLAN_ROOT_CAUSE_UNSUPPORTED'),
    ('checkpoint', 'CHECKPOINT_INCOMPATIBLE'),
])
def test_deterministic_replan_rejects_unknown_cause_or_checkpoint_drift(client, app, monkeypatch, mutation, code):
    _data, source, checkpoint = fail_after_checkpoint(client, app, monkeypatch)
    store = app.state.service.store
    if mutation == 'root_cause':
        with store.transaction() as db:
            changed = store.get('runs', source['id'])
            changed['exit_reason'] = 'VALIDATION_FAILED'
            db.execute('UPDATE runs SET doc=? WHERE id=?', (dumps(changed), changed['id']))
    else:
        def mutate(doc):
            doc['bindings']['resource_sha256'] = 'b' * 64
            doc['compatibility_digest'] = digest(dumps(doc['bindings']).encode())
        update_checkpoint(store, checkpoint, mutate)
    before = len(store.listing('runs'))
    rejected = client.post(f'/api/v1/runs/{source["id"]}/replans', json={}, headers={'Idempotency-Key': mutation})
    assert rejected.status_code == 409 and rejected.json()['error']['code'] == code
    assert len(store.listing('runs')) == before


@pytest.mark.parametrize('kind,expected', [
    ('resource', 'CHECKPOINT_INCOMPATIBLE'),
    ('task', 'CHECKPOINT_INCOMPATIBLE'),
    ('permissions', 'CHECKPOINT_INCOMPATIBLE'),
    ('adapter', 'CHECKPOINT_INCOMPATIBLE'),
    ('budget', 'CHECKPOINT_INCOMPATIBLE'),
    ('state', 'CHECKPOINT_STATE_INVALID'),
    ('source_run', 'CHECKPOINT_INCOMPATIBLE'),
    ('cancelled', 'CHECKPOINT_NOT_RESTORABLE'),
])
def test_checkpoint_restore_rejects_every_binding_without_creating_run(client, app, monkeypatch, kind, expected):
    data, source, checkpoint = fail_after_checkpoint(client, app, monkeypatch)
    store = app.state.service.store
    source_id = source['id']
    if kind == 'resource':
        def mutate(doc):
            doc['bindings']['resource_sha256'] = 'b' * 64
            doc['compatibility_digest'] = digest(dumps(doc['bindings']).encode())
        update_checkpoint(store, checkpoint, mutate)
    elif kind == 'task':
        with store.transaction() as db:
            task = store.get('tasks', data['task']['id'])
            task['objective'] = '数据库篡改后的不同目标'
            db.execute('UPDATE tasks SET doc=? WHERE id=?', (dumps(task), task['id']))
    elif kind == 'permissions':
        with store.transaction() as db:
            changed = store.get('runs', source_id)
            changed['effective_permissions']['allowed_tools'] = ['resource.inspect']
            db.execute('UPDATE runs SET doc=? WHERE id=?', (dumps(changed), source_id))
    elif kind == 'adapter':
        original = app.state.service.adapters['engine_mock_analytics'].describe
        monkeypatch.setattr(app.state.service.adapters['engine_mock_analytics'], 'describe',
                            lambda: {**original(), 'adapter_version': 'tampered'})
    elif kind == 'budget':
        def mutate(doc):
            doc['remaining_limits']['max_turns'] = 4
            doc['bindings']['remaining_limits_digest'] = digest(dumps(doc['remaining_limits']).encode())
            doc['compatibility_digest'] = digest(dumps(doc['bindings']).encode())
        update_checkpoint(store, checkpoint, mutate)
    elif kind == 'state':
        tampered_state = {'state_version': 'local_analytics_checkpoint@1', 'metrics': {'columns': []}}
        changed = copy.deepcopy(checkpoint)
        state_bytes = dumps(tampered_state).encode()
        changed['state_sha256'] = digest(state_bytes)
        changed['sha256'] = checkpoint_document_digest(changed)
        with store.transaction() as db:
            db.execute('UPDATE checkpoints SET doc=?,state=? WHERE id=?', (dumps(changed), state_bytes, checkpoint['id']))
    elif kind == 'source_run':
        update_checkpoint(store, checkpoint, lambda doc: doc.update(run_id='run_unrelated'))
    else:
        with store.transaction() as db:
            changed = store.get('runs', source_id)
            changed['status'], changed['exit_reason'] = 'cancelled', 'USER_CANCELLED'
            db.execute('UPDATE runs SET doc=? WHERE id=?', (dumps(changed), source_id))

    before = len(store.listing('runs'))
    response = client.post(f'/api/local/runs/{source_id}:restore', json={}, headers={'Idempotency-Key': 'bad-' + kind})
    assert response.status_code == 409
    assert response.json()['error']['code'] == expected
    assert len(store.listing('runs')) == before
    status = client.get(f'/api/local/runs/{source_id}/restore').json()
    assert status['eligible'] is False
    assert status['reason_code'] == expected


def test_checkpoint_restore_rejects_arguments_and_survives_restart(tmp_path, monkeypatch):
    target = tmp_path / 'checkpoint-restart.db'
    with TestClient(create_app(target), base_url='http://127.0.0.1') as client:
        data, source, checkpoint = fail_after_checkpoint(client, client.app, monkeypatch)
        rejected = client.post(f'/api/local/runs/{source["id"]}:restore', json={'plan': 'forbidden'},
                               headers={'Idempotency-Key': 'restore-arguments'})
        assert rejected.status_code == 422
        # Simulate a process crash after the append-only checkpoint but before a terminal event.
        with client.app.state.service.store.transaction() as db:
            interrupted = client.app.state.service.store.get('runs', source['id'])
            interrupted['status'], interrupted['exit_reason'] = 'running', None
            db.execute('UPDATE runs SET doc=? WHERE id=?', (dumps(interrupted), interrupted['id']))
    with TestClient(create_app(target), base_url='http://127.0.0.1') as client:
        run = client.get('/api/v1/runs/' + source['id']).json()
        assert run['status'] == 'failed' and run['exit_reason'] == 'SERVER_RESTARTED'
        assert client.get(f'/api/local/runs/{source["id"]}/restore').json()['eligible'] is True
        restored = client.post(f'/api/local/runs/{source["id"]}:restore', json={},
                               headers={'Idempotency-Key': 'restore-after-restart'})
        assert restored.status_code == 202
        client.app.state.service.execute(restored.json()['run_id'])
        assert client.get('/api/v1/runs/' + restored.json()['run_id']).json()['status'] == 'succeeded'


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


@pytest.mark.parametrize('fault,expected', [('event', 'ADAPTER_PROTOCOL_ERROR'),
                                          ('result', 'ADAPTER_PROTOCOL_ERROR'),
                                          ('version', 'ADAPTER_VERSION_MISMATCH'),
                                          ('cleanup', 'CLEANUP_FAILED')])
def test_adapter_boundaries(client, app, monkeypatch, fault, expected):
    data, _ = submit(client)
    run_id = data['initial_run']['id']
    adapter = app.state.service.adapters['engine_mock_analytics']
    if fault == 'event':
        monkeypatch.setattr(adapter, 'start_run', lambda req, emit, check: emit('run.succeeded', {}))
    elif fault == 'result':
        monkeypatch.setattr(adapter, 'start_run', lambda *args: {'success': True})
    elif fault == 'version':
        monkeypatch.setattr(adapter, 'describe', lambda: {'adapter_version': 'changed'})
    else:
        def broken_cleanup(run_id):
            raise RuntimeError('cleanup failure')
        monkeypatch.setattr(adapter, 'cleanup', broken_cleanup)
    app.state.service.execute(run_id)
    run = app.state.service.store.get('runs', run_id)
    assert run['status'] == 'failed' and run['exit_reason'] == expected
    assert app.state.service.store.artifact_list(run_id) == []


def test_readiness_never_enables_model(client):
    report = client.get('/api/v1/readiness')
    assert report.status_code == 200
    assert report.json()['model_route_enabled'] is False
    assert report.json()['blocking_items']
    engines = client.get('/api/v1/engines').json()['items']
    assert [e for e in engines if e['id'] == 'engine_smolagents_code'][0]['status'] == 'blocked'


def test_cancel_running_prevents_publication(client, app, monkeypatch):
    data, _ = submit(client)
    run_id = data['initial_run']['id']
    started, release = threading.Event(), threading.Event()
    from adapters import local
    original = local.analyze
    def slow(raw, check):
        started.set()
        assert release.wait(3)
        return original(raw, check)
    monkeypatch.setattr(local, 'analyze', slow)
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
