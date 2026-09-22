#!/usr/bin/env python3
"""Synthetic acceptance probe for ADR-0037; no message body, model or Runtime."""
import json
import sys
import tempfile
from pathlib import Path

from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.app import create_app  # noqa: E402


FIXTURE = json.loads((ROOT / 'fixtures/team-session-continuity-evaluation-v1.json').read_text())
CHANNEL = 'ch_session_eval'
THREAD = 'thread-session-eval'


def post(client, path, body, key, expected):
    response = client.post(path, json=body, headers={'Idempotency-Key': key})
    assert response.status_code == expected, response.text
    return response.json()


def create_session(client, key, inherited_handoff_id=None):
    body = {'actor_id': 'builder-01', 'workspace_id': 'ws_local', 'channel_id': CHANNEL}
    if inherited_handoff_id is not None:
        body['inherited_handoff_id'] = inherited_handoff_id
    return post(client, '/api/local/team/sessions', body, key, 201)


def handoff(client, session, key):
    return post(client, '/api/local/team/sessions/' + session['id'] + ':handoff', {
        'actor_id': 'builder-01', 'expected_session_version': session['version'], 'reason': 'manual_handoff',
    }, key, 201)


def main():
    with tempfile.TemporaryDirectory() as directory:
        with TestClient(create_app(Path(directory) / 'evaluation.db', False), base_url='http://127.0.0.1') as client:
            for agent_id in ('builder-01', 'reviewer-01'):
                post(client, '/api/local/team/workspaces/ws_local/agents', {
                    'actor_id': 'local_admin', 'workspace_id': 'ws_local', 'id': agent_id,
                    'kind': 'agent', 'display_name': agent_id, 'clearance': 'Restricted',
                }, 'session-eval-agent-' + agent_id, 201)
            post(client, '/api/local/team/workspaces/ws_local/channels', {
                'actor_id': 'local_admin', 'id': CHANNEL, 'title': 'Synthetic Session', 'data_class': 'Internal',
            }, 'session-eval-channel', 201)
            for agent_id, roles in (('builder-01', ['contributor']), ('reviewer-01', ['reviewer'])):
                post(client, '/api/local/team/channels/' + CHANNEL + '/memberships', {
                    'actor_id': 'local_admin', 'agent_id': agent_id, 'roles': roles,
                }, 'session-eval-member-' + agent_id, 201)
            task = post(client, '/api/local/team/tasks', {
                'workspace_id': 'ws_local', 'channel_id': CHANNEL, 'creator_id': 'local_admin', 'thread_id': THREAD,
                'title': 'Synthetic continuity task', 'objective': 'must not be copied into a Session snapshot',
                'requirements': ['R1 snapshot only has references'],
                'scope': {'allowed_paths': ['synthetic/'], 'forbidden_paths': ['secrets/'], 'resource_refs': ['repo:synthetic']},
                'stop_conditions': ['stop on scope change'],
                'gate': {'reviewer_id': 'reviewer-01', 'checks': ['check reference'],
                         'evidence_requirements': ['synthetic record'], 'on_reject': 'return builder'},
                'parent_task_id': None,
            }, 'session-eval-task', 201)
            task = post(client, '/api/local/team/tasks/' + task['id'] + ':claim', {
                'actor_id': 'builder-01', 'lease_seconds': 300,
            }, 'session-eval-task-claim', 200)
            first_attention = post(client, '/api/local/team/attention/items', {
                'actor_id': 'local_admin', 'workspace_id': 'ws_local', 'channel_id': CHANNEL, 'thread_id': THREAD,
                'source_ref': 'private-source-must-not-enter-snapshot', 'target_agent_id': 'builder-01',
                'kind': 'direct_mention',
            }, 'session-eval-attention-one', 201)
            predecessor = create_session(client, 'session-eval-predecessor')
            initial = predecessor['continuity']
            initial_metadata_only = (
                initial['current_task']['task_id'] == task['id']
                and initial['attention_items'][0]['item_id'] == first_attention['item']['id']
                and 'objective' not in json.dumps(initial)
                and 'source_ref' not in json.dumps(initial)
                and all(value == 0 for value in initial['omitted_counts'].values())
            )
            duplicate = client.post('/api/local/team/sessions', json={
                'actor_id': 'builder-01', 'workspace_id': 'ws_local', 'channel_id': CHANNEL,
            }, headers={'Idempotency-Key': 'session-eval-duplicate'})
            one_active = duplicate.status_code == 409 and duplicate.json()['error']['code'] == 'TEAM_SESSION_ACTIVE_CONFLICT'
            retired = handoff(client, predecessor['session'], 'session-eval-handoff')
            task_after = client.get('/api/local/team/tasks/' + task['id'] + '?actor_id=builder-01').json()['task']
            source_state_unchanged = task_after['version'] == task['version'] and task_after['status'] == 'in_progress'
            post(client, '/api/local/team/attention/items', {
                'actor_id': 'local_admin', 'workspace_id': 'ws_local', 'channel_id': CHANNEL, 'thread_id': THREAD,
                'source_ref': 'second-private-source', 'target_agent_id': 'builder-01', 'kind': 'direct_mention',
            }, 'session-eval-attention-two', 201)
            successor = create_session(client, 'session-eval-successor', retired['handoff']['id'])
            fresh_successor_snapshot = (
                retired['continuity']['thread_freshness'][0]['latest_sequence'] == 1
                and successor['continuity']['thread_freshness'][0]['latest_sequence'] == 2
                and successor['inherited_handoff']['consumed_by_session_id'] == successor['session']['id']
            )
            # Retire the successor first so the replay reaches the one-time
            # Handoff gate rather than being rejected earlier for active-slot
            # contention.  Session retirement itself never mutates Task or
            # Attention source state.
            handoff(client, successor['session'], 'session-eval-successor-handoff')
            replay = client.post('/api/local/team/sessions', json={
                'actor_id': 'builder-01', 'workspace_id': 'ws_local', 'channel_id': CHANNEL,
                'inherited_handoff_id': retired['handoff']['id'],
            }, headers={'Idempotency-Key': 'session-eval-consumed'})
            cross_owner = client.get('/api/local/team/sessions/' + successor['session']['id'] + '?actor_id=reviewer-01')
            handoff_is_one_time_and_owner_bound = (
                replay.status_code == 409 and replay.json()['error']['code'] == 'TEAM_SESSION_HANDOFF_CONSUMED'
                and cross_owner.status_code == 403
            )
            runtime = client.get('/api/local/team/sessions/runtime').json()

    results = {
        'bounded_metadata_only_snapshot': float(initial_metadata_only),
        'one_active_session_per_identity_channel': float(one_active),
        'handoff_does_not_mutate_source_task_state': float(source_state_unchanged),
        'successor_refreshes_current_snapshot': float(fresh_successor_snapshot),
        'handoff_is_one_time_and_owner_bound': float(handoff_is_one_time_and_owner_bound),
        'external_execution_calls': float(runtime['external_model_calls'] == runtime['external_tool_calls'] == 0),
    }
    report = {
        'evaluation_version': FIXTURE['evaluation_version'], 'scope': FIXTURE['scope'],
        'model_calls': 0, 'external_calls': 0, 'results': results,
        'passed': all(value >= FIXTURE['pass_threshold'] for value in results.values()),
        'not_evidence': [
            'This does not store message content, authenticate a caller, resume a Provider/Runtime session, or dispatch an Agent.',
            'The evaluation uses only synthetic metadata in a temporary SQLite database.',
        ],
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))
    if not report['passed']:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
