"""HA-0064: HTTP receipts are idempotent, current authorization is not cached."""
import copy
import json
from datetime import timedelta

import pytest
from fastapi.testclient import TestClient

from backend.analysis import Problem
from backend.app import create_app
from backend.team_coordination import iso_now
from test_team_list_failures import client, update_doc
from test_team_coordination import CREATE, ARTIFACT
from test_recovery_loop_guard import recovery_body, EVIDENCE


WS, CHANNEL, ACTOR = 'ws_replay64', 'ch_replay64', 'local_admin'
OPERATIONS = ['workspace', 'agent', 'workspace_grant', 'channel', 'channel_grant',
              'task_create', 'task_claim', 'task_handoff', 'task_submit', 'task_gate', 'task_close',
              'attention_create', 'attention_read', 'attention_claim', 'attention_release', 'attention_complete',
              'session_create', 'session_handoff', 'recovery_create', 'recovery_observe', 'recovery_try',
              'recovery_confirm', 'recovery_cancel', 'recovery_link', 'recovery_complete']
CHANNEL_READERS = [op for op in OPERATIONS if op not in {'workspace', 'agent', 'workspace_grant', 'channel_grant'}]


def request(client, receipt, **overrides):
    return client.post(receipt['path'], json=overrides.get('body', receipt['body']),
                       headers={'Idempotency-Key': overrides.get('key', receipt['key'])})


@pytest.fixture
def receipts(client):
    recorded = {}

    def send(name, path, body, status=201, record=True):
        receipt = {'path': '/api/local/' + path, 'body': copy.deepcopy(body), 'key': 'replay64-' + name}
        result = request(client, receipt)
        assert result.status_code == status, (name, result.text)
        receipt.update(status=status, result=result.json())
        if record:
            recorded[name] = receipt
        return result.json()

    send('workspace', 'team/workspaces', {'actor_id': ACTOR, 'id': WS, 'name': 'Replay workspace', 'data_class': 'Restricted'})
    send('agent', f'team/workspaces/{WS}/agents', {'actor_id': ACTOR, 'workspace_id': WS,
         'id': 'other-64', 'kind': 'agent', 'display_name': 'Replay peer', 'clearance': 'Restricted'})
    send('workspace_grant', f'team/workspaces/{WS}/memberships', {'actor_id': ACTOR,
         'agent_id': 'builder-60', 'role': 'member', 'clearance': 'Restricted'})
    send('channel', f'team/workspaces/{WS}/channels', {'actor_id': ACTOR, 'id': CHANNEL,
         'title': 'Replay channel', 'data_class': 'Restricted'})
    send('channel_grant', f'team/channels/{CHANNEL}/memberships', {'actor_id': ACTOR,
         'agent_id': 'builder-60', 'roles': ['contributor']})
    task_body = copy.deepcopy(CREATE)
    task_body.update(workspace_id=WS, channel_id=CHANNEL, creator_id=ACTOR)
    task_body['gate']['reviewer_id'] = ACTOR
    task = send('task_create', 'team/tasks', task_body)
    task = send('task_claim', f'team/tasks/{task["id"]}:claim', {'actor_id': ACTOR, 'lease_seconds': 300}, 200)
    case = send('recovery_create', 'recovery/cases', recovery_body(task, actor_id=ACTOR))
    case = send('recovery_observe', f'recovery/cases/{case["id"]}/observations', {
        'actor_id': ACTOR, 'expected_case_version': case['case_version'], 'kind': 'verified_progress',
        'turn': 1, 'operation_ref': 'publish.report', 'signature_sha256': 'f' * 64, 'evidence': [EVIDENCE]})['case']
    case = send('recovery_try', f'recovery/cases/{case["id"]}:try', {'actor_id': ACTOR,
        'expected_case_version': case['case_version'], 'strategy': 'retry_idempotent_step'}, 200)['case']
    case = send('recovery_confirm', f'recovery/cases/{case["id"]}:confirm', {'actor_id': ACTOR,
        'expected_case_version': case['case_version'], 'input_digest': 'd' * 64}, 200)['case']
    result = send('task_handoff', f'team/tasks/{task["id"]}/handoffs', {'actor_id': ACTOR,
        'expected_task_version': task['version'], 'summary': 'Replay verification', 'decisions': [],
        'artifact_refs': [ARTIFACT], 'evidence': ['Synthetic verification'], 'remaining': [], 'risks': [],
        'next_action': 'Review this receipt.'})
    task = result['task']
    case = send('recovery_link', f'recovery/cases/{case["id"]}:link-handoff', {'actor_id': ACTOR,
        'expected_case_version': case['case_version'], 'handoff_id': result['handoff']['id']}, 200)['case']
    task = send('task_submit', f'team/tasks/{task["id"]}:submit', {'actor_id': ACTOR,
        'expected_task_version': task['version']}, 200)
    result = send('task_gate', f'team/tasks/{task["id"]}/gate-decisions', {'reviewer_id': ACTOR,
        'expected_task_version': task['version'], 'decision': 'pass', 'evidence': [ARTIFACT], 'reason': 'Verified.'})
    send('recovery_complete', f'recovery/cases/{case["id"]}:complete', {'actor_id': ACTOR,
        'expected_case_version': case['case_version'], 'gate_decision_id': result['decision']['id']}, 200)
    task = send('cancel_task', 'team/tasks', task_body, record=False)
    task = send('cancel_claim', f'team/tasks/{task["id"]}:claim', {'actor_id': ACTOR, 'lease_seconds': 300}, 200, False)
    case = send('cancel_case', 'recovery/cases', recovery_body(task, actor_id=ACTOR), record=False)
    case = send('cancel_try', f'recovery/cases/{case["id"]}:try', {'actor_id': ACTOR,
        'expected_case_version': case['case_version'], 'strategy': 'retry_idempotent_step'}, 200, False)['case']
    send('recovery_cancel', f'recovery/cases/{case["id"]}:cancel', {'actor_id': ACTOR,
         'expected_case_version': case['case_version'], 'reason': 'Cancel only.'}, 200)
    task = send('close_task', 'team/tasks', task_body, record=False)
    send('task_close', f'team/tasks/{task["id"]}:close', {'actor_id': ACTOR,
         'expected_task_version': task['version'], 'reason': 'Stop tracking.'}, 200)
    result = send('attention_create', 'team/attention/items', {'actor_id': ACTOR, 'workspace_id': WS,
        'channel_id': CHANNEL, 'thread_id': 'thread-replay64', 'source_ref': 'source:replay64',
        'target_agent_id': ACTOR, 'kind': 'direct_mention'})
    item_id = result['item']['id']
    send('attention_read', f'team/channels/{CHANNEL}/threads/thread-replay64:read', {
        'actor_id': ACTOR, 'expected_latest_sequence': 1}, 200)
    item = send('attention_claim', f'team/attention/items/{item_id}:claim', {
        'actor_id': ACTOR, 'lease_seconds': 300}, 200)['item']
    send('attention_release', f'team/attention/items/{item_id}:release', {
        'actor_id': ACTOR, 'expected_item_version': item['version'], 'reason': 'Release for replay check.'}, 200)
    item = send('second_attention_claim', f'team/attention/items/{item_id}:claim', {
        'actor_id': ACTOR, 'lease_seconds': 300}, 200, False)['item']
    send('attention_complete', f'team/attention/items/{item_id}:complete', {
        'actor_id': ACTOR, 'expected_item_version': item['version'], 'freshness': {'read_sequence': 1}}, 200)
    session = send('session_create', 'team/sessions', {'actor_id': ACTOR, 'workspace_id': WS,
        'channel_id': CHANNEL})['session']
    send('session_handoff', f'team/sessions/{session["id"]}:handoff', {'actor_id': ACTOR,
        'expected_session_version': 1, 'reason': 'manual_handoff'})
    assert set(recorded) == set(OPERATIONS)
    return recorded


def db_snapshot(client):
    store = client.app.state.service.store
    with store.transaction() as db:
        names = [r['name'] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")]
        return db.total_changes, {name: [tuple(r) for r in db.execute('SELECT * FROM ' + name)] for name in names}


def reject(client, receipt, status, code):
    before = db_snapshot(client)
    response = request(client, receipt)
    assert response.status_code == status, response.text
    assert response.json()['error']['code'] == code
    assert set(response.json()) == {'error'}
    assert 'Replay channel' not in response.text and 'teamtask_' not in response.text
    assert db_snapshot(client) == before


@pytest.mark.parametrize('operation', OPERATIONS)
def test_replay_rechecks_suspended_actor(client, receipts, operation):
    update_doc(client, 'team_agent_identities', 'id=?', (ACTOR,), lambda d: d.update(status='suspended'))
    reject(client, receipts[operation], 403, 'TEAM_AGENT_SUSPENDED')


@pytest.mark.parametrize('operation', OPERATIONS)
@pytest.mark.parametrize('change,status,code', [
    ('revoked', 403, 'TEAM_WORKSPACE_ACCESS_DENIED'), ('archived', 409, 'TEAM_WORKSPACE_ARCHIVED'),
    ('clearance', 403, 'TEAM_DATA_CLEARANCE_DENIED'), ('corrupt', 500, 'TEAM_STATE_CORRUPT'),
])
def test_replay_rechecks_workspace_boundary(client, receipts, operation, change, status, code):
    if change == 'archived':
        update_doc(client, 'team_workspaces', 'id=?', (WS,), lambda d: d.update(status='archived'))
    else:
        patch = {'clearance': 'Public'} if change == 'clearance' else {'status': 'revoked' if change == 'revoked' else 'ACTIVE'}
        update_doc(client, 'team_workspace_memberships', 'workspace_id=? AND agent_id=?', (WS, ACTOR), lambda d: d.update(patch))
    reject(client, receipts[operation], status, code)


@pytest.mark.parametrize('operation', CHANNEL_READERS)
@pytest.mark.parametrize('change,status,code', [('revoked', 403, 'TEAM_CHANNEL_ACCESS_DENIED'),
                                              ('archived', 409, 'TEAM_CHANNEL_ARCHIVED')])
def test_replay_rechecks_channel_boundary(client, receipts, operation, change, status, code):
    if change == 'archived':
        update_doc(client, 'team_channels', 'id=?', (CHANNEL,), lambda d: d.update(status='archived'))
    else:
        update_doc(client, 'team_channel_memberships', 'channel_id=? AND agent_id=?', (CHANNEL, ACTOR), lambda d: d.update(status='revoked'))
    reject(client, receipts[operation], status, code)


@pytest.mark.parametrize('operation', [op for op in OPERATIONS if op.startswith(('task_', 'recovery_'))])
def test_replay_rechecks_current_channel_role(client, receipts, operation):
    update_doc(client, 'team_channel_memberships', 'channel_id=? AND agent_id=?',
               (CHANNEL, ACTOR), lambda d: d.update(roles=['observer']))
    reject(client, receipts[operation], 403, 'TEAM_CHANNEL_ROLE_DENIED')


@pytest.mark.parametrize('operation', OPERATIONS)
def test_valid_replay_is_original_receipt_without_any_write(client, receipts, operation):
    receipt = receipts[operation]
    before = db_snapshot(client)
    response = request(client, receipt)
    assert response.status_code == receipt['status'], response.text
    assert response.json() == receipt['result']
    assert db_snapshot(client) == before


def test_replay_does_not_expire_or_reexecute_old_claims(client, receipts):
    expired = (iso_now() - timedelta(seconds=1)).isoformat().replace('+00:00', 'Z')
    task_id = receipts['task_claim']['result']['id']
    update_doc(client, 'team_tasks', 'id=?', (task_id,), lambda d: d.update(
        lease={**receipts['task_claim']['result']['lease'], 'expires_at': expired}))
    case_id = receipts['recovery_create']['result']['id']
    update_doc(client, 'recovery_cases', 'id=?', (case_id,), lambda d: d.update(deadline_at=expired))
    before = db_snapshot(client)
    for name in ['task_claim', 'task_submit', 'recovery_create', 'recovery_try', 'recovery_complete', 'session_handoff']:
        response = request(client, receipts[name])
        assert response.status_code == receipts[name]['status'], response.text
        assert response.json() == receipts[name]['result']
    assert db_snapshot(client) == before


@pytest.mark.parametrize('operation', OPERATIONS)
def test_replay_access_backend_failure_is_not_cached_success(client, receipts, operation, monkeypatch):
    def fail(*args, **kwargs):
        raise Problem('ACCESS_BACKEND_UNAVAILABLE', 'Synthetic unavailable.', 503)
    monkeypatch.setattr(client.app.state.service.team_foundation, '_agent', fail)
    reject(client, receipts[operation], 503, 'ACCESS_BACKEND_UNAVAILABLE')


def test_replay_conflict_and_new_key_keep_original_semantics(client, receipts):
    receipt = receipts['session_create']
    changed = {**receipt['body'], 'actor_id': 'builder-60'}
    before = db_snapshot(client)
    result = request(client, receipt, body=changed)
    assert result.status_code == 409 and result.json()['error']['code'] == 'CONFLICT'
    assert db_snapshot(client) == before
    update_doc(client, 'team_channels', 'id=?', (CHANNEL,), lambda d: d.update(status='archived'))
    before = db_snapshot(client)
    for key in [receipt['key'], 'fresh-session-key']:
        result = request(client, receipt, key=key)
        assert result.status_code == 409 and result.json()['error']['code'] == 'TEAM_CHANNEL_ARCHIVED'
    assert db_snapshot(client) == before


def test_replay_rechecks_after_restart_and_after_permission_restored(client, receipts):
    receipt = receipts['session_handoff']
    update_doc(client, 'team_channel_memberships', 'channel_id=? AND agent_id=?',
               (CHANNEL, ACTOR), lambda d: d.update(status='revoked'))
    with client.app.state.service.store.transaction() as db:
        db_path = db.execute('PRAGMA database_list').fetchone()['file']
    client.__exit__(None, None, None)  # Finish lifespan and release the process DB lock.
    with TestClient(create_app(db_path, False), base_url='http://127.0.0.1', raise_server_exceptions=False) as restarted:
        reject(restarted, receipt, 403, 'TEAM_CHANNEL_ACCESS_DENIED')
        update_doc(restarted, 'team_channel_memberships', 'channel_id=? AND agent_id=?',
                   (CHANNEL, ACTOR), lambda d: d.update(status='active'))
        before = db_snapshot(restarted)
        result = request(restarted, receipt)
        assert result.status_code == receipt['status'] and result.json() == receipt['result']
        assert db_snapshot(restarted) == before


@pytest.mark.parametrize('operation', ['workspace', 'agent', 'workspace_grant', 'channel', 'channel_grant'])
def test_foundation_replay_requires_current_workspace_admin(client, receipts, operation):
    update_doc(client, 'team_workspace_memberships', 'workspace_id=? AND agent_id=?',
               (WS, ACTOR), lambda d: d.update(role='member'))
    reject(client, receipts[operation], 403, 'TEAM_WORKSPACE_ADMIN_REQUIRED')


@pytest.mark.parametrize('operation', ['session_create', 'session_handoff', 'attention_claim',
                                     'attention_release', 'attention_complete', 'recovery_create',
                                     'recovery_complete', 'task_gate'])
def test_replay_owner_target_and_reviewer_are_current(client, receipts, operation):
    receipt = receipts[operation]
    result = receipt['result']
    if operation.startswith('session_'):
        table, ident, patch, code = 'team_sessions', result['session']['id'], {'agent_id': 'builder-60'}, 'TEAM_SESSION_OWNER_FORBIDDEN'
    elif operation.startswith('attention_'):
        table, ident, patch, code = 'team_attention_items', result['item']['id'], {'target_agent_id': 'builder-60'}, 'TEAM_ATTENTION_TARGET_FORBIDDEN'
    elif operation.startswith('recovery_'):
        table, ident, patch, code = 'recovery_cases', result.get('case', result)['id'], {'owner_id': 'builder-60'}, 'RECOVERY_OWNER_REQUIRED'
    else:
        task = result['task']
        table, ident, patch, code = 'team_tasks', task['id'], {'gate': {**task['gate'], 'reviewer_id': 'builder-60'}}, 'TEAM_TASK_GATE_FORBIDDEN'
    update_doc(client, table, 'id=?', (ident,), lambda d: d.update(patch))
    reject(client, receipt, 403, code)


@pytest.mark.parametrize('operation', ['task_create', 'task_claim', 'task_handoff', 'task_submit',
                                     'task_gate', 'session_create', 'session_handoff', 'attention_create',
                                     'attention_claim', 'attention_release', 'attention_complete'])
def test_replay_cannot_authorize_old_scope_using_new_object_scope(client, receipts, operation):
    response = client.post(f'/api/local/team/workspaces/{WS}/channels', json={
        'actor_id': ACTOR, 'id': 'ch_other64', 'title': 'Other channel', 'data_class': 'Internal'},
        headers={'Idempotency-Key': 'other-channel'})
    assert response.status_code == 201, response.text
    receipt = receipts[operation]
    if operation.startswith('task_'):
        table, value = 'team_tasks', receipt['result'].get('task', receipt['result'])
    elif operation.startswith('session_'):
        table, value = 'team_sessions', receipt['result']['session']
    else:
        table, value = 'team_attention_items', receipt['result']['item']
    # Actor has valid access to both scopes; rejection must come from receipt binding.
    update_doc(client, table, 'id=?', (value['id'],), lambda d: d.update(channel_id='ch_other64'))
    reject(client, receipt, 409, 'TEAM_REPLAY_SCOPE_CHANGED')


@pytest.mark.parametrize('operation', ['recovery_create', 'recovery_try', 'recovery_cancel', 'recovery_complete'])
def test_recovery_replay_cannot_follow_a_different_task(client, receipts, operation):
    receipt = receipts[operation]
    case = receipt['result'].get('case', receipt['result'])
    other_task = receipts['task_close']['result']['id']
    update_doc(client, 'recovery_cases', 'id=?', (case['id'],), lambda d: d.update(team_task_id=other_task))
    reject(client, receipt, 409, 'TEAM_REPLAY_SCOPE_CHANGED')


@pytest.mark.parametrize('operation', OPERATIONS)
def test_replay_cannot_return_missing_primary_object(client, receipts, operation):
    receipt, result = receipts[operation], receipts[operation]['result']
    if operation == 'workspace':
        table, ident, code = 'team_workspaces', WS, 'TEAM_WORKSPACE_NOT_FOUND'
    elif operation in {'agent', 'workspace_grant'}:
        table, ident, code = 'team_agent_identities', ('other-64' if operation == 'agent' else 'builder-60'), 'TEAM_AGENT_NOT_FOUND'
    elif operation in {'channel', 'channel_grant', 'attention_read'}:
        table, ident, code = 'team_channels', CHANNEL, 'TEAM_CHANNEL_NOT_FOUND'
    elif operation.startswith('task_'):
        table, ident, code = 'team_tasks', result.get('task', result)['id'], 'TEAM_TASK_NOT_FOUND'
    elif operation.startswith('attention_'):
        table, ident, code = 'team_attention_items', result['item']['id'], 'TEAM_ATTENTION_NOT_FOUND'
    elif operation.startswith('session_'):
        table, ident, code = 'team_sessions', result['session']['id'], 'TEAM_SESSION_NOT_FOUND'
    else:
        table, ident, code = 'recovery_cases', result.get('case', result)['id'], 'RECOVERY_CASE_NOT_FOUND'
    # Corruption injection is restricted to this isolated test DB, not an API delete feature.
    store = client.app.state.service.store
    with store.lock:
        store.db.execute('PRAGMA foreign_keys=OFF')
        store.db.execute(f'DELETE FROM {table} WHERE id=?', (ident,))
        store.db.execute('PRAGMA foreign_keys=ON')
    reject(client, receipt, 404, code)


def test_readable_historical_grants_do_not_regrant_revoked_target(client, receipts):
    update_doc(client, 'team_workspace_memberships', 'workspace_id=? AND agent_id=?',
               (WS, 'builder-60'), lambda d: d.update(status='revoked'))
    update_doc(client, 'team_channel_memberships', 'channel_id=? AND agent_id=?',
               (CHANNEL, 'builder-60'), lambda d: d.update(status='revoked'))
    before = db_snapshot(client)
    for operation in ['workspace_grant', 'channel_grant']:
        response = request(client, receipts[operation])
        assert response.status_code == 201 and response.json() == receipts[operation]['result']
    assert db_snapshot(client) == before
