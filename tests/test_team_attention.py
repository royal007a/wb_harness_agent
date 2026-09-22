import json
from datetime import timedelta

import pytest
import yaml
from fastapi.testclient import TestClient
from jsonschema import Draft202012Validator

from backend.app import create_app
from backend.service import ROOT
from backend.team_attention import iso_now


ARTIFACT = {'kind': 'test_result', 'ref': 'checks/attention.log', 'sha256': 'a' * 64}
CHANNEL = 'ch_attention_local'


@pytest.fixture
def client(tmp_path):
    with TestClient(create_app(tmp_path / 'attention.db', False), base_url='http://127.0.0.1') as value:
        bootstrap(value)
        yield value


def bootstrap(client):
    for agent_id, kind in (('builder-01', 'agent'), ('reviewer-01', 'agent')):
        response = client.post('/api/local/team/workspaces/ws_local/agents', json={
            'actor_id': 'local_admin', 'workspace_id': 'ws_local', 'id': agent_id,
            'kind': kind, 'display_name': agent_id, 'clearance': 'Restricted',
        }, headers={'Idempotency-Key': 'attention-agent-' + agent_id})
        assert response.status_code == 201, response.text
    response = client.post('/api/local/team/workspaces/ws_local/channels', json={
        'actor_id': 'local_admin', 'id': CHANNEL, 'title': 'Attention Local', 'data_class': 'Internal',
    }, headers={'Idempotency-Key': 'attention-channel'})
    assert response.status_code == 201, response.text
    for agent_id, roles in (('builder-01', ['contributor']), ('reviewer-01', ['reviewer'])):
        response = client.post('/api/local/team/channels/' + CHANNEL + '/memberships', json={
            'actor_id': 'local_admin', 'agent_id': agent_id, 'roles': roles,
        }, headers={'Idempotency-Key': 'attention-member-' + agent_id})
        assert response.status_code == 201, response.text


def attention(client, *, target='builder-01', kind='direct_mention', thread='thread-attention-01',
              actor='local_admin', source='source:message-01', key='attention-create'):
    response = client.post('/api/local/team/attention/items', json={
        'actor_id': actor, 'workspace_id': 'ws_local', 'channel_id': CHANNEL,
        'thread_id': thread, 'source_ref': source, 'target_agent_id': target, 'kind': kind,
    }, headers={'Idempotency-Key': key})
    assert response.status_code == 201, response.text
    return response.json()


def read_latest(client, actor, thread, sequence, key):
    response = client.post('/api/local/team/channels/' + CHANNEL + '/threads/' + thread + ':read', json={
        'actor_id': actor, 'expected_latest_sequence': sequence,
    }, headers={'Idempotency-Key': key})
    assert response.status_code == 200, response.text
    return response.json()


def claim(client, item_id, key):
    response = client.post('/api/local/team/attention/items/' + item_id + ':claim', json={
        'actor_id': 'builder-01', 'lease_seconds': 300,
    }, headers={'Idempotency-Key': key})
    assert response.status_code == 200, response.text
    return response.json()


def task_body(thread='thread-task-fresh'):
    return {
        'workspace_id': 'ws_local', 'channel_id': CHANNEL, 'creator_id': 'local_admin', 'thread_id': thread,
        'title': 'Freshness must protect this task', 'objective': '证明新指令阻断旧交接和验收。',
        'requirements': ['R1：必须先读取最新 sequence。'],
        'scope': {'allowed_paths': ['tests/'], 'forbidden_paths': ['secrets/'], 'resource_refs': ['repo:local']},
        'stop_conditions': ['发现新提示时停止旧决定。'],
        'gate': {'reviewer_id': 'reviewer-01', 'checks': ['核对 sequence。'],
                 'evidence_requirements': ['检查记录。'], 'on_reject': '退回 builder-01。'},
        'parent_task_id': None,
    }


def handoff_body(task, freshness=None):
    body = {
        'actor_id': 'builder-01', 'expected_task_version': task['version'],
        'summary': '已完成注意力新鲜度检查。', 'decisions': ['只按已读最新 sequence 交接。'],
        'artifact_refs': [ARTIFACT], 'evidence': ['attention test'], 'remaining': [], 'risks': [],
        'next_action': '请 reviewer-01 检查。',
    }
    if freshness is not None:
        body['freshness'] = {'read_sequence': freshness}
    return body


def test_attention_inbox_is_metadata_only_and_authorized(client):
    runtime = client.get('/api/local/team/attention/runtime')
    assert runtime.status_code == 200
    assert runtime.json()['agent_runtime'] == 'not_connected'
    assert runtime.json()['external_model_calls'] == runtime.json()['external_tool_calls'] == 0
    created = attention(client)
    assert created['item']['priority'] == 80 and created['item']['sequence'] == 1
    assert created['work_mark']['status'] == 'open'
    assert set(created['item']) == {
        'schema_version', 'id', 'workspace_id', 'channel_id', 'thread_id', 'source_ref', 'author_id',
        'target_agent_id', 'kind', 'priority', 'sequence', 'status', 'version', 'lease', 'created_at', 'updated_at',
    }
    inbox = client.get('/api/local/team/inbox?actor_id=builder-01')
    assert inbox.status_code == 200 and [entry['item']['id'] for entry in inbox.json()['items']] == [created['item']['id']]
    assert client.get('/api/local/team/inbox?actor_id=reviewer-01').json()['items'] == []
    invalid = client.post('/api/local/team/attention/items', json={
        'actor_id': 'local_admin', 'workspace_id': 'ws_local', 'channel_id': CHANNEL,
        'thread_id': 'thread-attention-01', 'source_ref': 'source:message-02',
        'target_agent_id': 'builder-01', 'kind': 'direct_mention', 'message': 'must never persist',
    }, headers={'Idempotency-Key': 'attention-invalid-extra'})
    assert invalid.status_code == 422 and invalid.json()['error']['code'] == 'TEAM_ATTENTION_CONTRACT_INVALID'
    url_source = client.post('/api/local/team/attention/items', json={
        'actor_id': 'local_admin', 'workspace_id': 'ws_local', 'channel_id': CHANNEL,
        'thread_id': 'thread-attention-01', 'source_ref': 'https://attachment.example/private.pdf',
        'target_agent_id': 'builder-01', 'kind': 'direct_mention',
    }, headers={'Idempotency-Key': 'attention-invalid-url'})
    assert url_source.status_code == 422 and url_source.json()['error']['code'] == 'TEAM_ATTENTION_CONTRACT_INVALID'
    human_only = client.post('/api/local/team/attention/items', json={
        'actor_id': 'builder-01', 'workspace_id': 'ws_local', 'channel_id': CHANNEL,
        'thread_id': 'thread-attention-01', 'source_ref': 'source:message-03',
        'target_agent_id': 'builder-01', 'kind': 'human_correction',
    }, headers={'Idempotency-Key': 'attention-agent-correction'})
    assert human_only.status_code == 403 and human_only.json()['error']['code'] == 'TEAM_ATTENTION_HUMAN_SOURCE_REQUIRED'


def test_work_mark_survives_expired_lease_and_one_identity_claims_one_item(client):
    first = attention(client, source='source:lease-01', key='attention-lease-first')
    second = attention(client, source='source:lease-02', key='attention-lease-second')
    claimed = claim(client, first['item']['id'], 'attention-lease-claim-first')
    conflict = client.post('/api/local/team/attention/items/' + second['item']['id'] + ':claim', json={
        'actor_id': 'builder-01', 'lease_seconds': 300,
    }, headers={'Idempotency-Key': 'attention-lease-claim-second'})
    assert conflict.status_code == 409 and conflict.json()['error']['code'] == 'TEAM_ATTENTION_LEASE_CONFLICT'
    with client.app.state.service.store.transaction() as db:
        row = db.execute('SELECT doc FROM team_attention_items WHERE id=?', (first['item']['id'],)).fetchone()
        expired = json.loads(row['doc'])
        expired['lease']['expires_at'] = (iso_now() - timedelta(seconds=1)).isoformat().replace('+00:00', 'Z')
        db.execute('UPDATE team_attention_items SET doc=? WHERE id=?', (json.dumps(expired), first['item']['id']))
    inbox = client.get('/api/local/team/inbox?actor_id=builder-01')
    assert inbox.status_code == 200
    by_id = {entry['item']['id']: entry for entry in inbox.json()['items']}
    assert by_id[first['item']['id']]['item']['status'] == 'pending'
    assert by_id[first['item']['id']]['work_mark']['status'] == 'open'
    released = claim(client, first['item']['id'], 'attention-lease-reclaim')
    release = client.post('/api/local/team/attention/items/' + first['item']['id'] + ':release', json={
        'actor_id': 'builder-01', 'expected_item_version': released['item']['version'], 'reason': 'awaiting newer context',
    }, headers={'Idempotency-Key': 'attention-lease-release'})
    assert release.status_code == 200 and release.json()['work_mark']['status'] == 'open'


def test_new_sequence_blocks_stale_attention_completion_until_read_again(client):
    first = attention(client, source='source:fresh-01', key='attention-fresh-first')
    claimed = claim(client, first['item']['id'], 'attention-fresh-claim')
    read_latest(client, 'builder-01', 'thread-attention-01', 1, 'attention-fresh-read-one')
    attention(client, source='source:fresh-02', key='attention-fresh-second')
    stale = client.post('/api/local/team/attention/items/' + first['item']['id'] + ':complete', json={
        'actor_id': 'builder-01', 'expected_item_version': claimed['item']['version'], 'freshness': {'read_sequence': 1},
    }, headers={'Idempotency-Key': 'attention-fresh-complete-stale'})
    assert stale.status_code == 409 and stale.json()['error']['code'] == 'TEAM_FRESHNESS_REQUIRED'
    still_open = client.get('/api/local/team/inbox?actor_id=builder-01').json()['items']
    first_state = next(entry for entry in still_open if entry['item']['id'] == first['item']['id'])
    assert first_state['item']['status'] == 'in_progress' and first_state['work_mark']['status'] == 'in_progress'
    read_latest(client, 'builder-01', 'thread-attention-01', 2, 'attention-fresh-read-two')
    completed = client.post('/api/local/team/attention/items/' + first['item']['id'] + ':complete', json={
        'actor_id': 'builder-01', 'expected_item_version': claimed['item']['version'], 'freshness': {'read_sequence': 2},
    }, headers={'Idempotency-Key': 'attention-fresh-complete-current'})
    assert completed.status_code == 200
    assert completed.json()['item']['status'] == 'completed' and completed.json()['work_mark']['status'] == 'cleared'


def test_task_handoff_submit_and_gate_all_require_current_thread_read(client):
    created = client.post('/api/local/team/tasks', json=task_body(), headers={'Idempotency-Key': 'fresh-task-create'})
    assert created.status_code == 201, created.text
    task = created.json()
    claimed = client.post('/api/local/team/tasks/' + task['id'] + ':claim', json={
        'actor_id': 'builder-01', 'lease_seconds': 300,
    }, headers={'Idempotency-Key': 'fresh-task-claim'})
    assert claimed.status_code == 200, claimed.text
    task = claimed.json()
    attention(client, thread='thread-task-fresh', source='source:task-01', key='fresh-task-attention-one')
    stale_handoff = client.post('/api/local/team/tasks/' + task['id'] + '/handoffs', json=handoff_body(task),
                                headers={'Idempotency-Key': 'fresh-task-handoff-stale'})
    assert stale_handoff.status_code == 409 and stale_handoff.json()['error']['code'] == 'TEAM_FRESHNESS_REQUIRED'
    read_latest(client, 'builder-01', 'thread-task-fresh', 1, 'fresh-task-builder-read-one')
    handoff = client.post('/api/local/team/tasks/' + task['id'] + '/handoffs', json=handoff_body(task, freshness=1),
                          headers={'Idempotency-Key': 'fresh-task-handoff-current'})
    assert handoff.status_code == 201, handoff.text
    task = handoff.json()['task']
    attention(client, thread='thread-task-fresh', source='source:task-02', key='fresh-task-attention-two')
    stale_submit = client.post('/api/local/team/tasks/' + task['id'] + ':submit', json={
        'actor_id': 'builder-01', 'expected_task_version': task['version'], 'freshness': {'read_sequence': 1},
    }, headers={'Idempotency-Key': 'fresh-task-submit-stale'})
    assert stale_submit.status_code == 409 and stale_submit.json()['error']['code'] == 'TEAM_FRESHNESS_REQUIRED'
    read_latest(client, 'builder-01', 'thread-task-fresh', 2, 'fresh-task-builder-read-two')
    submitted = client.post('/api/local/team/tasks/' + task['id'] + ':submit', json={
        'actor_id': 'builder-01', 'expected_task_version': task['version'], 'freshness': {'read_sequence': 2},
    }, headers={'Idempotency-Key': 'fresh-task-submit-current'})
    assert submitted.status_code == 200, submitted.text
    task = submitted.json()
    attention(client, target='reviewer-01', thread='thread-task-fresh', source='source:task-03',
              key='fresh-task-attention-reviewer')
    stale_gate = client.post('/api/local/team/tasks/' + task['id'] + '/gate-decisions', json={
        'reviewer_id': 'reviewer-01', 'expected_task_version': task['version'], 'decision': 'pass',
        'evidence': [ARTIFACT], 'reason': 'checking current context',
    }, headers={'Idempotency-Key': 'fresh-task-gate-stale'})
    assert stale_gate.status_code == 409 and stale_gate.json()['error']['code'] == 'TEAM_FRESHNESS_REQUIRED'
    read_latest(client, 'reviewer-01', 'thread-task-fresh', 3, 'fresh-task-reviewer-read')
    passed = client.post('/api/local/team/tasks/' + task['id'] + '/gate-decisions', json={
        'reviewer_id': 'reviewer-01', 'expected_task_version': task['version'], 'decision': 'pass',
        'evidence': [ARTIFACT], 'reason': 'checking current context', 'freshness': {'read_sequence': 3},
    }, headers={'Idempotency-Key': 'fresh-task-gate-current'})
    assert passed.status_code == 201 and passed.json()['task']['status'] == 'done'


def test_contract_persistence_and_openapi_are_explicit(tmp_path):
    database = tmp_path / 'restart-attention.db'
    with TestClient(create_app(database, False), base_url='http://127.0.0.1') as local:
        bootstrap(local)
        created = attention(local, source='source:restart-01', key='attention-restart')
        read_latest(local, 'builder-01', 'thread-attention-01', 1, 'attention-restart-read')
    with TestClient(create_app(database, False), base_url='http://127.0.0.1') as restarted:
        inbox = restarted.get('/api/local/team/inbox?actor_id=builder-01').json()
        assert inbox['items'][0]['item']['id'] == created['item']['id']
        assert inbox['items'][0]['read_sequence'] == 1
        contract = json.loads((ROOT / 'specs/v1/team-attention.schema.json').read_text())
        Draft202012Validator.check_schema(contract)
        validator = Draft202012Validator({'$ref': '#/$defs/inbox_list', '$defs': contract['$defs']})
        assert validator.is_valid(inbox)
        static = yaml.safe_load((ROOT / 'specs/v1/openapi.yaml').read_text())
        runtime_paths = restarted.app.openapi()['paths']
        pairs = {
            '/local/team/attention/runtime': '/api/local/team/attention/runtime',
            '/local/team/inbox': '/api/local/team/inbox',
            '/local/team/attention/items': '/api/local/team/attention/items',
            '/local/team/attention/items/{itemId}:claim': '/api/local/team/attention/items/{item_id}:claim',
            '/local/team/attention/items/{itemId}:release': '/api/local/team/attention/items/{item_id}:release',
            '/local/team/attention/items/{itemId}:complete': '/api/local/team/attention/items/{item_id}:complete',
            '/local/team/channels/{channelId}/threads/{threadId}:read': '/api/local/team/channels/{channel_id}/threads/{thread_id}:read',
        }
        for static_path, runtime_path in pairs.items():
            assert static_path in static['paths'] and runtime_path in runtime_paths
        assert runtime_paths['/api/local/team/attention/items']['post']['responses']['201']['content']['application/json']['schema'] == {
            '$ref': '#/components/schemas/ha0038_attention_mutation_result'
        }
