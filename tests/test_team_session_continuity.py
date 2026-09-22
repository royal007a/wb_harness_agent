import json

import pytest
import yaml
from fastapi.testclient import TestClient
from jsonschema import Draft202012Validator

from backend.app import create_app
from backend.service import ROOT


CHANNEL = 'ch_session_local'
THREAD = 'thread-session-state'
ARTIFACT = {'kind': 'test_result', 'ref': 'checks/session.log', 'sha256': 'a' * 64}


@pytest.fixture
def client(tmp_path):
    with TestClient(create_app(tmp_path / 'session.db', False), base_url='http://127.0.0.1') as value:
        bootstrap(value)
        yield value


def bootstrap(client):
    for agent_id, kind in (('builder-01', 'agent'), ('reviewer-01', 'agent')):
        response = client.post('/api/local/team/workspaces/ws_local/agents', json={
            'actor_id': 'local_admin', 'workspace_id': 'ws_local', 'id': agent_id,
            'kind': kind, 'display_name': agent_id, 'clearance': 'Restricted',
        }, headers={'Idempotency-Key': 'session-agent-' + agent_id})
        assert response.status_code == 201, response.text
    response = client.post('/api/local/team/workspaces/ws_local/channels', json={
        'actor_id': 'local_admin', 'id': CHANNEL, 'title': 'Session Local', 'data_class': 'Internal',
    }, headers={'Idempotency-Key': 'session-channel'})
    assert response.status_code == 201, response.text
    for agent_id, roles in (('builder-01', ['contributor']), ('reviewer-01', ['reviewer'])):
        response = client.post('/api/local/team/channels/' + CHANNEL + '/memberships', json={
            'actor_id': 'local_admin', 'agent_id': agent_id, 'roles': roles,
        }, headers={'Idempotency-Key': 'session-member-' + agent_id})
        assert response.status_code == 201, response.text


def create_session(client, actor='builder-01', inherited_handoff_id=None, key='session-create'):
    body = {'actor_id': actor, 'workspace_id': 'ws_local', 'channel_id': CHANNEL}
    if inherited_handoff_id is not None:
        body['inherited_handoff_id'] = inherited_handoff_id
    response = client.post('/api/local/team/sessions', json=body, headers={'Idempotency-Key': key})
    assert response.status_code == 201, response.text
    return response.json()


def session_handoff(client, session, key='session-handoff', reason='manual_handoff'):
    response = client.post('/api/local/team/sessions/' + session['id'] + ':handoff', json={
        'actor_id': 'builder-01', 'expected_session_version': session['version'], 'reason': reason,
    }, headers={'Idempotency-Key': key})
    assert response.status_code == 201, response.text
    return response.json()


def create_task(client):
    response = client.post('/api/local/team/tasks', json={
        'workspace_id': 'ws_local', 'channel_id': CHANNEL, 'creator_id': 'local_admin', 'thread_id': THREAD,
        'title': 'Session snapshot task', 'objective': 'This content must not enter a session snapshot.',
        'requirements': ['R1 current task reference'],
        'scope': {'allowed_paths': ['tests/'], 'forbidden_paths': ['secrets/'], 'resource_refs': ['repo:local']},
        'stop_conditions': ['stop on scope change'],
        'gate': {'reviewer_id': 'reviewer-01', 'checks': ['check snapshot'],
                 'evidence_requirements': ['check record'], 'on_reject': 'return builder'},
        'parent_task_id': None,
    }, headers={'Idempotency-Key': 'session-task-create'})
    assert response.status_code == 201, response.text
    task = response.json()
    claimed = client.post('/api/local/team/tasks/' + task['id'] + ':claim', json={
        'actor_id': 'builder-01', 'lease_seconds': 300,
    }, headers={'Idempotency-Key': 'session-task-claim'})
    assert claimed.status_code == 200, claimed.text
    return claimed.json()


def attention(client, source, key):
    response = client.post('/api/local/team/attention/items', json={
        'actor_id': 'local_admin', 'workspace_id': 'ws_local', 'channel_id': CHANNEL,
        'thread_id': THREAD, 'source_ref': source, 'target_agent_id': 'builder-01', 'kind': 'direct_mention',
    }, headers={'Idempotency-Key': key})
    assert response.status_code == 201, response.text
    return response.json()


def thread_entry(snapshot, thread=THREAD):
    return next(item for item in snapshot['thread_freshness'] if item['thread_id'] == thread)


def test_runtime_owner_boundary_and_one_active_session(client):
    runtime = client.get('/api/local/team/sessions/runtime')
    assert runtime.status_code == 200
    assert runtime.json()['agent_runtime'] == runtime.json()['runtime_telemetry'] == 'not_connected'
    assert runtime.json()['external_model_calls'] == runtime.json()['external_tool_calls'] == 0
    created = create_session(client)
    snapshot = created['continuity']
    assert set(snapshot) == {
        'schema_version', 'workspace_id', 'channel_id', 'agent_id', 'current_task', 'owned_tasks',
        'pending_reviews', 'available_tasks', 'attention_items', 'thread_freshness', 'omitted_counts', 'generated_at',
    }
    assert snapshot['current_task'] is None and snapshot['attention_items'] == []
    assert all(value == 0 for value in snapshot['omitted_counts'].values())
    duplicate = client.post('/api/local/team/sessions', json={
        'actor_id': 'builder-01', 'workspace_id': 'ws_local', 'channel_id': CHANNEL,
    }, headers={'Idempotency-Key': 'session-duplicate'})
    assert duplicate.status_code == 409 and duplicate.json()['error']['code'] == 'TEAM_SESSION_ACTIVE_CONFLICT'
    forbidden = client.get('/api/local/team/sessions/' + created['session']['id'] + '?actor_id=reviewer-01')
    assert forbidden.status_code == 403 and forbidden.json()['error']['code'] == 'TEAM_SESSION_OWNER_FORBIDDEN'
    invalid = client.post('/api/local/team/sessions', json={
        'actor_id': 'reviewer-01', 'workspace_id': 'ws_local', 'channel_id': CHANNEL, 'summary': 'not persisted',
    }, headers={'Idempotency-Key': 'session-unknown-field'})
    assert invalid.status_code == 422 and invalid.json()['error']['code'] == 'TEAM_SESSION_CONTRACT_INVALID'


def test_handoff_snapshot_is_referenced_only_and_successor_refreshes_current_state(client):
    task = create_task(client)
    first_attention = attention(client, 'source:session-01', 'session-attention-one')
    predecessor = create_session(client, key='session-predecessor')
    initial = predecessor['continuity']
    assert initial['current_task']['task_id'] == task['id']
    assert initial['owned_tasks'][0]['task_version'] == task['version']
    assert initial['attention_items'][0]['item_id'] == first_attention['item']['id']
    assert thread_entry(initial)['latest_sequence'] == 1 and thread_entry(initial)['read_sequence'] == 0
    assert 'objective' not in json.dumps(initial) and 'source_ref' not in json.dumps(initial)
    handoff = session_handoff(client, predecessor['session'])
    assert handoff['session']['status'] == 'retired'
    assert handoff['handoff']['snapshot'] == handoff['continuity']
    task_after_handoff = client.get('/api/local/team/tasks/' + task['id'] + '?actor_id=builder-01').json()['task']
    assert task_after_handoff['version'] == task['version'] and task_after_handoff['status'] == 'in_progress'
    attention(client, 'source:session-02', 'session-attention-two')
    successor = create_session(client, inherited_handoff_id=handoff['handoff']['id'], key='session-successor')
    assert successor['session']['inherited_handoff_id'] == handoff['handoff']['id']
    assert successor['inherited_handoff']['consumed_by_session_id'] == successor['session']['id']
    assert thread_entry(handoff['continuity'])['latest_sequence'] == 1
    assert thread_entry(successor['continuity'])['latest_sequence'] == 2
    successor_handoff = session_handoff(client, successor['session'], key='session-successor-handoff')
    assert successor_handoff['session']['status'] == 'retired'
    consumed = client.post('/api/local/team/sessions', json={
        'actor_id': 'builder-01', 'workspace_id': 'ws_local', 'channel_id': CHANNEL,
        'inherited_handoff_id': handoff['handoff']['id'],
    }, headers={'Idempotency-Key': 'session-consumed'})
    assert consumed.status_code == 409 and consumed.json()['error']['code'] == 'TEAM_SESSION_HANDOFF_CONSUMED'


def test_handoff_scope_version_and_idempotency_are_enforced(client):
    builder = create_session(client, key='session-scope-builder')
    stale = client.post('/api/local/team/sessions/' + builder['session']['id'] + ':handoff', json={
        'actor_id': 'builder-01', 'expected_session_version': 99, 'reason': 'manual_handoff',
    }, headers={'Idempotency-Key': 'session-handoff-stale'})
    assert stale.status_code == 409 and stale.json()['error']['code'] == 'TEAM_SESSION_VERSION_CONFLICT'
    handoff = session_handoff(client, builder['session'], key='session-scope-handoff')
    cross_identity = client.post('/api/local/team/sessions', json={
        'actor_id': 'reviewer-01', 'workspace_id': 'ws_local', 'channel_id': CHANNEL,
        'inherited_handoff_id': handoff['handoff']['id'],
    }, headers={'Idempotency-Key': 'session-cross-identity'})
    assert cross_identity.status_code == 403
    replay = client.post('/api/local/team/sessions/' + builder['session']['id'] + ':handoff', json={
        'actor_id': 'builder-01', 'expected_session_version': builder['session']['version'], 'reason': 'manual_handoff',
    }, headers={'Idempotency-Key': 'session-scope-handoff'})
    assert replay.status_code == 201 and replay.json() == handoff


def test_sessions_persist_and_static_and_dynamic_openapi_match(tmp_path):
    database = tmp_path / 'session-restart.db'
    with TestClient(create_app(database, False), base_url='http://127.0.0.1') as local:
        bootstrap(local)
        predecessor = create_session(local, key='session-restart-create')
        handoff = session_handoff(local, predecessor['session'], key='session-restart-handoff')
        successor = create_session(local, inherited_handoff_id=handoff['handoff']['id'], key='session-restart-successor')
        session_id = successor['session']['id']
    with TestClient(create_app(database, False), base_url='http://127.0.0.1') as restarted:
        detail = restarted.get('/api/local/team/sessions/' + session_id + '?actor_id=builder-01')
        assert detail.status_code == 200, detail.text
        result = detail.json()
        assert result['session']['status'] == 'active'
        assert result['inherited_handoff']['consumed_by_session_id'] == session_id
        assert result['runtime']['automatic_rotation'] is False
        contract = json.loads((ROOT / 'specs/v1/team-session-continuity.schema.json').read_text())
        Draft202012Validator.check_schema(contract)
        validator = Draft202012Validator({'$ref': '#/$defs/session_detail', '$defs': contract['$defs']})
        assert validator.is_valid(result)
        static = yaml.safe_load((ROOT / 'specs/v1/openapi.yaml').read_text())
        runtime_paths = restarted.app.openapi()['paths']
        pairs = {
            '/local/team/sessions/runtime': '/api/local/team/sessions/runtime',
            '/local/team/sessions': '/api/local/team/sessions',
            '/local/team/sessions/{sessionId}': '/api/local/team/sessions/{session_id}',
            '/local/team/sessions/{sessionId}:handoff': '/api/local/team/sessions/{session_id}:handoff',
        }
        for static_path, runtime_path in pairs.items():
            assert static_path in static['paths'] and runtime_path in runtime_paths
        assert runtime_paths['/api/local/team/sessions/{session_id}:handoff']['post']['responses']['201']['content']['application/json']['schema'] == {
            '$ref': '#/components/schemas/ha0041_session_handoff_result'
        }
