#!/usr/bin/env python3
"""Synthetic acceptance probe for ADR-0036; no transport, Agent or model."""
import json
import sys
import tempfile
from pathlib import Path

from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.app import create_app  # noqa: E402


FIXTURE = json.loads((ROOT / 'fixtures/team-attention-evaluation-v1.json').read_text())
ARTIFACT = {'kind': 'test_result', 'ref': 'synthetic/attention.log', 'sha256': 'a' * 64}
CHANNEL = 'ch_attention_eval'
THREAD = 'thread-attention-eval'


def post(client, path, body, key, expected):
    response = client.post(path, json=body, headers={'Idempotency-Key': key})
    assert response.status_code == expected, response.text
    return response.json()


def attention_body(target, source, kind='direct_mention'):
    return {
        'actor_id': 'local_admin', 'workspace_id': 'ws_local', 'channel_id': CHANNEL,
        'thread_id': THREAD, 'source_ref': source, 'target_agent_id': target, 'kind': kind,
    }


def task_body():
    return {
        'workspace_id': 'ws_local', 'channel_id': CHANNEL, 'creator_id': 'local_admin', 'thread_id': THREAD,
        'title': 'synthetic fresh task', 'objective': 'prove new sequence blocks stale delivery',
        'requirements': ['R1 current sequence is mandatory'],
        'scope': {'allowed_paths': ['synthetic/'], 'forbidden_paths': ['secrets/'], 'resource_refs': ['repo:synthetic']},
        'stop_conditions': ['stop on newer attention metadata'],
        'gate': {'reviewer_id': 'reviewer-01', 'checks': ['check sequence'],
                 'evidence_requirements': ['synthetic record'], 'on_reject': 'return builder'},
        'parent_task_id': None,
    }


def main():
    with tempfile.TemporaryDirectory() as directory:
        with TestClient(create_app(Path(directory) / 'evaluation.db', False), base_url='http://127.0.0.1') as client:
            for agent_id in ('builder-01', 'reviewer-01'):
                post(client, '/api/local/team/workspaces/ws_local/agents', {
                    'actor_id': 'local_admin', 'workspace_id': 'ws_local', 'id': agent_id,
                    'kind': 'agent', 'display_name': agent_id, 'clearance': 'Restricted',
                }, 'attention-eval-agent-' + agent_id, 201)
            post(client, '/api/local/team/workspaces/ws_local/channels', {
                'actor_id': 'local_admin', 'id': CHANNEL, 'title': 'Synthetic Attention', 'data_class': 'Internal',
            }, 'attention-eval-channel', 201)
            for agent_id, roles in (('builder-01', ['contributor']), ('reviewer-01', ['reviewer'])):
                post(client, '/api/local/team/channels/' + CHANNEL + '/memberships', {
                    'actor_id': 'local_admin', 'agent_id': agent_id, 'roles': roles,
                }, 'attention-eval-member-' + agent_id, 201)
            first = post(client, '/api/local/team/attention/items', attention_body('builder-01', 'source:eval-01'),
                         'attention-eval-first', 201)
            second = post(client, '/api/local/team/attention/items', attention_body('builder-01', 'source:eval-02'),
                          'attention-eval-second', 201)
            inbox = client.get('/api/local/team/inbox?actor_id=builder-01').json()
            priority_and_metadata = (
                [entry['item']['sequence'] for entry in inbox['items']] == [1, 2]
                and inbox['items'][0]['item']['priority'] == 80
                and 'message' not in inbox['items'][0]['item']
            )
            claim_first = post(client, '/api/local/team/attention/items/' + first['item']['id'] + ':claim', {
                'actor_id': 'builder-01', 'lease_seconds': 300,
            }, 'attention-eval-claim-first', 200)
            claim_second = client.post('/api/local/team/attention/items/' + second['item']['id'] + ':claim', json={
                'actor_id': 'builder-01', 'lease_seconds': 300,
            }, headers={'Idempotency-Key': 'attention-eval-claim-second'})
            single_lease = claim_second.status_code == 409 and claim_second.json()['error']['code'] == 'TEAM_ATTENTION_LEASE_CONFLICT'
            post(client, '/api/local/team/channels/' + CHANNEL + '/threads/' + THREAD + ':read', {
                'actor_id': 'builder-01', 'expected_latest_sequence': 2,
            }, 'attention-eval-read-two', 200)
            third = post(client, '/api/local/team/attention/items', attention_body('builder-01', 'source:eval-03'),
                         'attention-eval-third', 201)
            stale_complete = client.post('/api/local/team/attention/items/' + first['item']['id'] + ':complete', json={
                'actor_id': 'builder-01', 'expected_item_version': claim_first['item']['version'],
                'freshness': {'read_sequence': 2},
            }, headers={'Idempotency-Key': 'attention-eval-complete-stale'})
            stale_completion_blocked = (
                stale_complete.status_code == 409 and stale_complete.json()['error']['code'] == 'TEAM_FRESHNESS_REQUIRED')
            post(client, '/api/local/team/channels/' + CHANNEL + '/threads/' + THREAD + ':read', {
                'actor_id': 'builder-01', 'expected_latest_sequence': 3,
            }, 'attention-eval-read-three', 200)
            complete = post(client, '/api/local/team/attention/items/' + first['item']['id'] + ':complete', {
                'actor_id': 'builder-01', 'expected_item_version': claim_first['item']['version'],
                'freshness': {'read_sequence': 3},
            }, 'attention-eval-complete-current', 200)
            work_mark_semantics = complete['work_mark']['status'] == 'cleared'
            task = post(client, '/api/local/team/tasks', task_body(), 'attention-eval-task', 201)
            task = post(client, '/api/local/team/tasks/' + task['id'] + ':claim', {
                'actor_id': 'builder-01', 'lease_seconds': 300,
            }, 'attention-eval-task-claim', 200)
            stale_handoff = client.post('/api/local/team/tasks/' + task['id'] + '/handoffs', json={
                'actor_id': 'builder-01', 'expected_task_version': task['version'], 'summary': 'stale synthetic handoff',
                'decisions': [], 'artifact_refs': [ARTIFACT], 'evidence': ['synthetic'], 'remaining': [],
                'risks': [], 'next_action': 'review', 'freshness': {'read_sequence': 2},
            }, headers={'Idempotency-Key': 'attention-eval-task-handoff-stale'})
            task_freshness_enforced = (
                stale_handoff.status_code == 409 and stale_handoff.json()['error']['code'] == 'TEAM_FRESHNESS_REQUIRED')
            runtime = client.get('/api/local/team/attention/runtime').json()

    results = {
        'metadata_only_priority_and_order': float(priority_and_metadata),
        'single_identity_attention_lease': float(single_lease),
        'stale_completion_blocked': float(stale_completion_blocked),
        'work_mark_clears_only_after_fresh_completion': float(work_mark_semantics),
        'task_handoff_freshness_enforced': float(task_freshness_enforced),
        'external_execution_calls': float(runtime['external_model_calls'] == runtime['external_tool_calls'] == 0),
    }
    report = {
        'evaluation_version': FIXTURE['evaluation_version'], 'scope': FIXTURE['scope'],
        'model_calls': 0, 'external_calls': 0, 'results': results,
        'passed': all(value >= FIXTURE['pass_threshold'] for value in results.values()),
        'not_evidence': [
            'This does not deliver a message, authenticate a caller, dispatch an Agent, invoke a model, tool or provider.',
            'The evaluation uses only synthetic metadata in a temporary SQLite database.',
        ],
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))
    if not report['passed']:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
