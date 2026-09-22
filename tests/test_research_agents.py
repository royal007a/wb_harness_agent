import copy
import json
import time
from concurrent.futures import ThreadPoolExecutor

import pytest
from fastapi.testclient import TestClient
from jsonschema import Draft202012Validator

from backend.app import create_app
from backend.analysis import Problem
from backend.research_agents import CONTRACT, skill_manifest
from backend.store import dumps


BODY = {
    'companies': ['demo_a'], 'concurrency': 3, 'failure_policy': 'continue_with_warning',
    'scenario': 'complete', 'timeout_seconds': 60, 'max_steps': 7,
}


@pytest.fixture
def client(tmp_path):
    with TestClient(create_app(tmp_path / 'research-agents.db', False), base_url='http://127.0.0.1') as value:
        yield value


def submit(client, **changes):
    response = client.post('/api/local/research-agents', json={**BODY, **changes},
                           headers={'Idempotency-Key': str(time.monotonic_ns())})
    assert response.status_code == 202, response.text
    return response.json()['initial_run']['id']


def events(service, run_id, event_type):
    return [item for item in service.store.events(run_id) if item['event_type'] == event_type]


def test_three_agents_skill_snapshots_and_auditable_report(client):
    root = submit(client, companies=['demo_a', 'demo_b'], max_steps=13)
    service = client.app.state.service
    service.execute(root)
    detail = client.get('/api/local/research-agents/' + root).json()
    assert detail['mode'] == 'research_agent_simulation@1'
    assert detail['run']['status'] == 'succeeded'
    assert detail['runtime'] == {
        'id': 'research_agent_simulation@1', 'model_calls': 0, 'provider_calls': 0,
        'network_calls': 0, 'external_tool_calls': 0,
    }
    assert len(detail['children']) == 6
    trace_id = service.store.events(root)[0]['trace_id']
    roles = set()
    for child in detail['children']:
        run, assignment, agent = child['run'], child['assignment'], child['agent']
        roles.add(agent['role'])
        assert run['status'] == 'succeeded'
        assert run['parent_run_id'] == root
        assert run['effective_permissions']['allowed_tools'] == ['resource.inspect']
        assert run['effective_limits']['max_turns'] == agent['max_turns'] == 2
        assert agent['runtime'] == 'deterministic_simulation'
        assert agent['skill'] == skill_manifest(assignment['role'])
        schema = {'$ref': '#/$defs/agent_definition', '$defs': CONTRACT['$defs']}
        assert Draft202012Validator(schema).is_valid(agent)
        assert events(service, run['id'], 'agent.turn.started')
        assert events(service, run['id'], 'skill.loaded')
        assert events(service, run['id'], 'tool.call.completed')
        assert events(service, run['id'], 'agent.observation.received')
        assert events(service, run['id'], 'agent.finalized')
        assert all(event['trace_id'] == trace_id for event in service.store.events(run['id']))
        output = client.get('/api/v1/artifacts/' + child['artifacts'][0]['id'] + '/content').json()
        assert output['evidence'][0]['resource_id'] == assignment['resource_id']
        assert output['synthetic'] is True
    assert roles == {'financial', 'industry', 'risk'}
    manifest = next(item for item in detail['artifacts'] if item['name'] == 'research-agent-manifest.json')
    result = client.get('/api/v1/artifacts/' + manifest['id'] + '/content').json()
    assert result['coverage'] == 'complete' and result['successful'] == 6 and result['failed'] == 0
    assert result['usage']['model_calls'] == result['usage']['provider_calls'] == result['usage']['network_calls'] == 0
    assert result['risk_assessment'] == 'not_assessed'


@pytest.mark.parametrize('changes', [
    {'companies': []}, {'concurrency': 4}, {'max_steps': 6}, {'scenario': 'live'}, {'roles': ['financial']},
])
def test_bad_request_has_no_side_effect(client, changes):
    service = client.app.state.service
    response = client.post('/api/local/research-agents', json={**BODY, **changes}, headers={'Idempotency-Key': 'bad'})
    assert response.status_code == 422
    assert not service.store.listing('tasks') and not service.store.listing('runs')


def test_idempotency_rerun_and_partial_risk_evidence(client):
    service = client.app.state.service
    request = {**BODY, 'scenario': 'missing_risk'}
    first = service.research_agents.create(copy.deepcopy(request), 'same')
    assert service.research_agents.create(copy.deepcopy(request), 'same') == first
    assert client.post('/api/local/research-agents', json={**request, 'concurrency': 1},
                       headers={'Idempotency-Key': 'same'}).status_code == 409
    root, task_id = first['initial_run']['id'], first['task']['id']
    service.execute(root)
    detail = service.research_agents.detail(root)
    assert detail['run']['status'] == 'succeeded'
    assert detail['run']['exit_reason'] == 'COMPLETED_WITH_WARNINGS'
    assert [child['run']['status'] for child in detail['children']].count('failed') == 1
    manifest = json.loads(service.store.db.execute('SELECT body FROM artifacts WHERE run_id=? AND doc LIKE ?',
                                                   (root, '%research-agent-manifest.json%')).fetchone()[0])
    assert manifest['coverage'] == 'partial' and manifest['risk_assessment'] == 'not_assessed'
    rerun = client.post('/api/v1/tasks/' + task_id + '/runs', json={'based_on_run_id': root},
                        headers={'Idempotency-Key': 'rerun'})
    assert rerun.status_code == 202, rerun.text
    assert rerun.json()['id'] != root and len(service.research_agents.children(rerun.json()['id'])) == 3


@pytest.mark.parametrize('fault', ['skill', 'tool_permission', 'resource_scope'])
def test_contract_drift_or_scope_expansion_is_rejected(client, monkeypatch, fault):
    service = client.app.state.service
    root = submit(client, failure_policy='fail_parent')
    child = service.research_agents.children(root)[0]
    if fault == 'skill':
        from backend import research_agents
        original = research_agents.skill_manifest
        monkeypatch.setattr(research_agents, 'skill_manifest', lambda role: {**original(role), 'sha256': '0' * 64})
    elif fault == 'tool_permission':
        child['effective_permissions']['allowed_tools'] = ['resource.inspect', 'network.fetch']
        with service.store.transaction() as db:
            db.execute('UPDATE runs SET doc=? WHERE id=?', (dumps(child), child['id']))
    else:
        original = service.research_agents.tool_runtime.inspect

        def out_of_scope(call, *, assignment, permissions):
            call = {**call, 'input': {'resource_id': 'res_' + '0' * 64}}
            return original(call, assignment=assignment, permissions=permissions)

        monkeypatch.setattr(service.research_agents.tool_runtime, 'inspect', out_of_scope)
    service.execute(root)
    detail = service.research_agents.detail(root)
    assert detail['run']['status'] == 'failed'
    assert any(child['run']['exit_reason'] in {'SKILL_VERSION_MISMATCH', 'FORBIDDEN', 'RESOURCE_SCOPE_VIOLATION'}
               for child in detail['children'])
    assert not detail['artifacts']


def test_global_concurrency_and_queued_child_cancel(client, monkeypatch):
    service = client.app.state.service
    roots = [submit(client, companies=['demo_a']), submit(client, companies=['demo_b'])]
    original = service.research_agents.tool_runtime.inspect
    entered, release = __import__('threading').Event(), __import__('threading').Event()
    lock = __import__('threading').Lock()
    active = peak = 0

    def slow(call, *, assignment, permissions):
        nonlocal active, peak
        with lock:
            active += 1
            peak = max(peak, active)
            if active == 3:
                entered.set()
        try:
            release.wait(3)
            return original(call, assignment=assignment, permissions=permissions)
        finally:
            with lock:
                active -= 1

    monkeypatch.setattr(service.research_agents.tool_runtime, 'inspect', slow)
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(service.execute, root) for root in roots]
        assert entered.wait(3)
        release.set()
        for future in futures:
            future.result(timeout=5)
    assert peak == 3
    root = submit(client)
    child = service.research_agents.children(root)[0]['id']
    assert client.post('/api/v1/runs/' + child + ':cancel').status_code == 200
    service.execute(root)
    assert service.research_agents.detail(root)['run']['exit_reason'] == 'COMPLETED_WITH_WARNINGS'


def test_running_tree_is_closed_on_restart(tmp_path):
    database = tmp_path / 'research-agents-restart.db'
    with TestClient(create_app(database, False), base_url='http://127.0.0.1') as local:
        root = submit(local)
        service = local.app.state.service
        with service.store.transaction() as db:
            run = service.store.get('runs', root)
            run['status'] = 'running'
            service.store.event(db, run, 'run.started')
    with TestClient(create_app(database, True), base_url='http://127.0.0.1') as restarted:
        detail = restarted.get('/api/local/research-agents/' + root).json()
        assert detail['run']['status'] == 'failed'
        assert detail['run']['exit_reason'] == 'SERVER_RESTARTED'
        assert all(child['run']['status'] == 'cancelled' for child in detail['children'])


def test_openapi_and_engine_state_are_explicit(client):
    openapi = client.get('/openapi.json').json()
    operation = openapi['paths']['/api/local/research-agents']['post']
    assert operation['requestBody']['content']['application/json']['schema'] == {
        '$ref': '#/components/schemas/research_agent_request'
    }
    engines = client.get('/api/v1/engines').json()['items']
    engine = next(item for item in engines if item['id'] == 'engine_research_multi_agent_simulation')
    assert engine['status'] == 'available' and '非 Claude' in engine['description']
