#!/usr/bin/env python3
"""Synthetic acceptance probe for ADR-0035; no real identity provider or Agent."""
import json
import sys
import tempfile
from pathlib import Path

from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.app import create_app  # noqa: E402


FIXTURE = json.loads((ROOT / 'fixtures/team-foundation-evaluation-v1.json').read_text())


def post(client, path, body, key, expected):
    response = client.post(path, json=body, headers={'Idempotency-Key': key})
    assert response.status_code == expected, response.text
    return response.json()


def main():
    with tempfile.TemporaryDirectory() as directory:
        with TestClient(create_app(Path(directory) / 'evaluation.db', False), base_url='http://127.0.0.1') as client:
            for agent_id, clearance in (('builder-01', 'Restricted'), ('reviewer-01', 'Restricted'),
                                        ('observer-01', 'Internal')):
                post(client, '/api/local/team/workspaces/ws_local/agents', {
                    'actor_id': 'local_admin', 'workspace_id': 'ws_local', 'id': agent_id,
                    'kind': 'agent', 'display_name': agent_id, 'clearance': clearance,
                }, 'foundation-eval-agent-' + agent_id, 201)
            post(client, '/api/local/team/workspaces/ws_local/channels', {
                'actor_id': 'local_admin', 'id': 'ch_foundation_eval', 'title': 'Synthetic Foundation',
                'data_class': 'Internal',
            }, 'foundation-eval-channel', 201)
            post(client, '/api/local/team/workspaces/ws_local/channels', {
                'actor_id': 'local_admin', 'id': 'ch_foundation_restricted', 'title': 'Synthetic Restricted',
                'data_class': 'Restricted',
            }, 'foundation-eval-restricted-channel', 201)
            for agent_id, roles in (('builder-01', ['contributor']), ('reviewer-01', ['reviewer']),
                                    ('observer-01', ['observer'])):
                post(client, '/api/local/team/channels/ch_foundation_eval/memberships', {
                    'actor_id': 'local_admin', 'agent_id': agent_id, 'roles': roles,
                }, 'foundation-eval-member-' + agent_id, 201)
            low_clearance = client.post('/api/local/team/channels/ch_foundation_restricted/memberships', json={
                'actor_id': 'local_admin', 'agent_id': 'observer-01', 'roles': ['observer'],
            }, headers={'Idempotency-Key': 'foundation-eval-low-clearance'})
            channels = client.get('/api/local/team/workspaces/ws_local/channels?actor_id=observer-01').json()['items']
            task = post(client, '/api/local/team/tasks', {
                'workspace_id': 'ws_local', 'channel_id': 'ch_foundation_eval', 'creator_id': 'local_admin',
                'thread_id': None, 'title': 'synthetic boundary task', 'objective': 'verify roles',
                'requirements': ['R1 role check'],
                'scope': {'allowed_paths': ['internal/'], 'forbidden_paths': ['secrets/'], 'resource_refs': ['repo:synthetic']},
                'stop_conditions': ['stop on invalid role'],
                'gate': {'reviewer_id': 'reviewer-01', 'checks': ['check role'],
                         'evidence_requirements': ['test'], 'on_reject': 'return'},
                'parent_task_id': None,
            }, 'foundation-eval-task', 201)
            observer_claim = client.post(f'/api/local/team/tasks/{task["id"]}:claim', json={
                'actor_id': 'observer-01', 'lease_seconds': 300,
            }, headers={'Idempotency-Key': 'foundation-eval-observer-claim'})
            builder_claim = client.post(f'/api/local/team/tasks/{task["id"]}:claim', json={
                'actor_id': 'builder-01', 'lease_seconds': 300,
            }, headers={'Idempotency-Key': 'foundation-eval-builder-claim'})
            with client.app.state.service.store.transaction() as db:
                db.execute('INSERT INTO team_tasks VALUES(?,?,?)', ('teamtask_' + 'e' * 32, None, json.dumps({
                    'schema_version': 'team-task@1', 'id': 'teamtask_' + 'e' * 32, 'status': 'todo',
                })))
            legacy = client.get('/api/local/team/tasks/teamtask_' + 'e' * 32 + '?actor_id=builder-01')
            runtime = client.get('/api/local/team/foundation/runtime').json()

    results = {
        'channel_visibility_isolated': float([row['id'] for row in channels] == ['ch_foundation_eval']),
        'clearance_enforced': float(low_clearance.status_code == 403 and low_clearance.json()['error']['code'] == 'TEAM_DATA_CLEARANCE_DENIED'),
        'task_role_enforced': float(observer_claim.status_code == 403 and builder_claim.status_code == 200),
        'legacy_not_auto_authorized': float(legacy.status_code == 409 and legacy.json()['error']['code'] == 'TEAM_TASK_LEGACY_UNBOUND'),
        'external_execution_calls': float(runtime['external_model_calls'] == runtime['external_tool_calls'] == 0),
    }
    report = {
        'evaluation_version': FIXTURE['evaluation_version'], 'scope': FIXTURE['scope'],
        'model_calls': 0, 'external_calls': 0, 'results': results,
        'passed': all(value >= FIXTURE['pass_threshold'] for value in results.values()),
        'not_evidence': [
            'This does not authenticate an HTTP caller, validate a token/OIDC session, or test a real Agent identity.',
            'The evaluation uses only synthetic metadata in a temporary SQLite database and invokes no model, tool, network or message delivery.',
        ],
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))
    if not report['passed']:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
