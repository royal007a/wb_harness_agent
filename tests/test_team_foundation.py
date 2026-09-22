import json

import pytest
import yaml
from fastapi.testclient import TestClient
from jsonschema import Draft202012Validator

from backend.app import create_app
from backend.service import ROOT


ARTIFACT = {'kind': 'test_result', 'ref': 'checks/foundation.log', 'sha256': 'a' * 64}


@pytest.fixture
def client(tmp_path):
    with TestClient(create_app(tmp_path / 'foundation.db', False), base_url='http://127.0.0.1') as value:
        yield value


def create_agent(client, agent_id, clearance='Restricted', kind='agent'):
    response = client.post('/api/local/team/workspaces/ws_local/agents', json={
        'actor_id': 'local_admin', 'workspace_id': 'ws_local', 'id': agent_id, 'kind': kind,
        'display_name': agent_id, 'clearance': clearance,
    }, headers={'Idempotency-Key': 'agent-' + agent_id})
    assert response.status_code == 201, response.text
    return response.json()


def create_channel(client, channel_id, data_class='Internal'):
    response = client.post('/api/local/team/workspaces/ws_local/channels', json={
        'actor_id': 'local_admin', 'id': channel_id, 'title': channel_id, 'data_class': data_class,
    }, headers={'Idempotency-Key': 'channel-' + channel_id})
    assert response.status_code == 201, response.text
    return response.json()['channel']


def grant_channel(client, channel_id, agent_id, roles):
    response = client.post(f'/api/local/team/channels/{channel_id}/memberships', json={
        'actor_id': 'local_admin', 'agent_id': agent_id, 'roles': roles,
    }, headers={'Idempotency-Key': 'channel-member-' + channel_id + '-' + agent_id})
    assert response.status_code == 201, response.text
    return response.json()


def task_body(channel_id='ch_team_boundary'):
    return {
        'workspace_id': 'ws_local', 'channel_id': channel_id, 'creator_id': 'local_admin',
        'thread_id': None, 'title': '受限协作任务', 'objective': '只验证 Channel 授权与交接边界。',
        'requirements': ['R1：成员与数据等级必须被检查。'],
        'scope': {'allowed_paths': ['internal/'], 'forbidden_paths': ['secrets/'], 'resource_refs': ['repo:local']},
        'stop_conditions': ['权限不满足时停止。'],
        'gate': {'reviewer_id': 'reviewer-01', 'checks': ['检查访问与角色。'],
                 'evidence_requirements': ['测试记录。'], 'on_reject': '交回 builder-01。'},
        'parent_task_id': None,
    }


def test_bootstrap_is_explicit_protocol_boundary(client):
    runtime = client.get('/api/local/team/foundation/runtime').json()
    assert runtime['protocol_identity_authentication'] == 'not_connected'
    assert runtime['agent_runtime'] == 'not_connected'
    assert runtime['external_model_calls'] == runtime['external_tool_calls'] == 0
    assert runtime['message_delivery'] == 'not_implemented'
    workspaces = client.get('/api/local/team/workspaces?actor_id=local_admin')
    assert workspaces.status_code == 200
    assert [item['id'] for item in workspaces.json()['items']] == ['ws_local']
    detail = client.get('/api/local/team/workspaces/ws_local?actor_id=local_admin').json()
    assert detail['memberships'][0]['agent_id'] == 'local_admin'
    assert detail['memberships'][0]['role'] == 'owner'


def test_workspace_channel_clearance_and_visibility_boundaries(client):
    create_agent(client, 'internal-reader', clearance='Internal')
    create_agent(client, 'restricted-reader')
    create_channel(client, 'ch_internal_boundary', 'Internal')
    create_channel(client, 'ch_restricted_boundary', 'Restricted')
    grant_channel(client, 'ch_internal_boundary', 'internal-reader', ['observer'])
    denied = client.post('/api/local/team/channels/ch_restricted_boundary/memberships', json={
        'actor_id': 'local_admin', 'agent_id': 'internal-reader', 'roles': ['observer'],
    }, headers={'Idempotency-Key': 'restricted-low-clearance'})
    assert denied.status_code == 403 and denied.json()['error']['code'] == 'TEAM_DATA_CLEARANCE_DENIED'
    grant_channel(client, 'ch_restricted_boundary', 'restricted-reader', ['observer'])
    visible = client.get('/api/local/team/workspaces/ws_local/channels?actor_id=internal-reader')
    assert visible.status_code == 200
    assert [item['id'] for item in visible.json()['items']] == ['ch_internal_boundary']
    hidden = client.get('/api/local/team/channels/ch_restricted_boundary?actor_id=internal-reader')
    assert hidden.status_code == 403 and hidden.json()['error']['code'] == 'TEAM_DATA_CLEARANCE_DENIED'


def test_task_paths_require_channel_roles_and_do_not_leak_legacy_records(client):
    create_agent(client, 'builder-01')
    create_agent(client, 'reviewer-01')
    create_agent(client, 'observer-01')
    create_channel(client, 'ch_team_boundary')
    grant_channel(client, 'ch_team_boundary', 'builder-01', ['contributor'])
    grant_channel(client, 'ch_team_boundary', 'reviewer-01', ['reviewer'])
    grant_channel(client, 'ch_team_boundary', 'observer-01', ['observer'])
    created = client.post('/api/local/team/tasks', json=task_body(), headers={'Idempotency-Key': 'task-create'})
    assert created.status_code == 201, created.text
    task = created.json()
    assert task['schema_version'] == 'team-task@2' and task['created_by_id'] == 'local_admin'
    assert client.get('/api/local/team/tasks?actor_id=observer-01').json()['items'][0]['id'] == task['id']
    denied = client.post(f'/api/local/team/tasks/{task["id"]}:claim', json={
        'actor_id': 'observer-01', 'lease_seconds': 300,
    }, headers={'Idempotency-Key': 'observer-claim'})
    assert denied.status_code == 403 and denied.json()['error']['code'] == 'TEAM_CHANNEL_ROLE_DENIED'
    claimed = client.post(f'/api/local/team/tasks/{task["id"]}:claim', json={
        'actor_id': 'builder-01', 'lease_seconds': 300,
    }, headers={'Idempotency-Key': 'builder-claim'})
    assert claimed.status_code == 200, claimed.text
    handoff = client.post(f'/api/local/team/tasks/{task["id"]}/handoffs', json={
        'actor_id': 'builder-01', 'expected_task_version': claimed.json()['version'], 'summary': '完成边界检查。',
        'decisions': [], 'artifact_refs': [ARTIFACT], 'evidence': ['test'], 'remaining': [], 'risks': [],
        'next_action': '请 reviewer 审核。',
    }, headers={'Idempotency-Key': 'builder-handoff'})
    assert handoff.status_code == 201, handoff.text
    submitted = client.post(f'/api/local/team/tasks/{task["id"]}:submit', json={
        'actor_id': 'builder-01', 'expected_task_version': handoff.json()['task']['version'],
    }, headers={'Idempotency-Key': 'builder-submit'})
    assert submitted.status_code == 200, submitted.text
    decision = client.post(f'/api/local/team/tasks/{task["id"]}/gate-decisions', json={
        'reviewer_id': 'reviewer-01', 'expected_task_version': submitted.json()['version'], 'decision': 'pass',
        'evidence': [ARTIFACT], 'reason': '角色和证据满足。',
    }, headers={'Idempotency-Key': 'reviewer-pass'})
    assert decision.status_code == 201 and decision.json()['task']['status'] == 'done'
    with client.app.state.service.store.transaction() as db:
        db.execute('INSERT INTO team_tasks VALUES(?,?,?)', ('teamtask_' + 'f' * 32, None, json.dumps({
            'schema_version': 'team-task@1', 'id': 'teamtask_' + 'f' * 32, 'status': 'todo',
        })))
    listed = client.get('/api/local/team/tasks?actor_id=builder-01').json()['items']
    assert [item['id'] for item in listed] == [task['id']]
    legacy = client.get('/api/local/team/tasks/teamtask_' + 'f' * 32 + '?actor_id=builder-01')
    assert legacy.status_code == 409 and legacy.json()['error']['code'] == 'TEAM_TASK_LEGACY_UNBOUND'


def test_foundation_rejects_sensitive_metadata_persists_and_exposes_openapi(client, tmp_path):
    rejected = client.post('/api/local/team/workspaces/ws_local/agents', json={
        'actor_id': 'local_admin', 'workspace_id': 'ws_local', 'id': 'secret-agent', 'kind': 'agent',
        'display_name': 'password=not-stored', 'clearance': 'Internal',
    }, headers={'Idempotency-Key': 'sensitive-agent'})
    assert rejected.status_code == 422 and rejected.json()['error']['code'] == 'SENSITIVE_INPUT_REJECTED'
    schema = json.loads((ROOT / 'specs/v1/team-foundation.schema.json').read_text())
    Draft202012Validator.check_schema(schema)
    static = yaml.safe_load((ROOT / 'specs/v1/openapi.yaml').read_text())
    assert {
        '/local/team/foundation/runtime', '/local/team/workspaces', '/local/team/workspaces/{workspaceId}',
        '/local/team/workspaces/{workspaceId}/agents', '/local/team/workspaces/{workspaceId}/memberships',
        '/local/team/workspaces/{workspaceId}/channels', '/local/team/channels/{channelId}',
        '/local/team/channels/{channelId}/memberships',
    } <= set(static['paths'])
    assert '/api/local/team/foundation/runtime' in client.app.openapi()['paths']
