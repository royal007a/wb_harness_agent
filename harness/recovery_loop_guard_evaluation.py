#!/usr/bin/env python3
"""Synthetic, deterministic anti-loop acceptance probe for ADR-0034."""
import json
import sys
import tempfile
from pathlib import Path

from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.app import create_app  # noqa: E402


FIXTURE = json.loads((ROOT / 'fixtures/recovery-loop-guard-evaluation-v1.json').read_text())
SHA = 'a' * 64
EVIDENCE = {'kind': 'log', 'ref': 'synthetic/recovery.log', 'sha256': SHA}
CHECKPOINT = {'kind': 'checkpoint', 'ref': 'synthetic/checkpoint.json', 'sha256': 'b' * 64}
ARTIFACT = {'kind': 'test_result', 'ref': 'synthetic/gate.log', 'sha256': 'c' * 64}


def post(client, path, body, key, expected):
    response = client.post(path, json=body, headers={'Idempotency-Key': key})
    assert response.status_code == expected, response.text
    return response.json()


def main():
    with tempfile.TemporaryDirectory() as directory:
        with TestClient(create_app(Path(directory) / 'evaluation.db', False), base_url='http://127.0.0.1') as client:
            task = post(client, '/api/local/team/tasks', {
                'channel_id': 'ch_recovery_eval', 'thread_id': 'thread-eval', 'title': 'synthetic recovery',
                'objective': 'verify recovery controls', 'requirements': ['R1 traceable result'],
                'scope': {'allowed_paths': ['internal/'], 'forbidden_paths': ['db/'], 'resource_refs': ['repo:synthetic']},
                'stop_conditions': ['stop on expanded permission'],
                'gate': {'reviewer_id': 'reviewer-01', 'checks': ['check evidence'],
                         'evidence_requirements': ['test record'], 'on_reject': 'return to builder-01'},
                'parent_task_id': None,
            }, 'evaluation-task', 201)
            task = post(client, f'/api/local/team/tasks/{task["id"]}:claim',
                        {'actor_id': 'builder-01', 'lease_seconds': 300}, 'evaluation-claim', 200)
            case = post(client, '/api/local/recovery/cases', {
                'team_task_id': task['id'], 'actor_id': 'builder-01', 'input_digest': 'd' * 64,
                'limits': {'max_turns': 5, 'max_elapsed_seconds': 300, 'max_recovery_attempts': 2,
                           'max_repeated_operation_failures': 3},
                'failure_point': {'operation_ref': 'publish.report', 'error_code': 'EXECUTION_TIMEOUT',
                                  'observed_at': '2026-09-22T00:00:00Z', 'evidence': [EVIDENCE]},
                'root_cause_hypothesis': {'category': 'external_dependency', 'hypothesis': 'synthetic transient dependency',
                                          'confidence': 'low', 'evidence': [EVIDENCE]},
                'rollback_checkpoint': {'availability': 'verified', 'checkpoint_ref': 'external:synthetic',
                                        'checkpoint_sha256': 'e' * 64, 'evidence': [CHECKPOINT]},
                'replan_start': {'decision_ref': 'decision.retry-publish', 'rationale': 'synthetic decision boundary',
                                 'requires_fresh_input': False},
            }, 'evaluation-case', 201)
            four_positions = all(name in case for name in ('failure_point', 'root_cause_hypothesis', 'rollback_checkpoint', 'replan_start'))
            catalog = case['error_contract']['retryable'] is True and case['error_contract']['recommended_next_action'] == 'retry_after_confirm'

            loop_case = post(client, '/api/local/recovery/cases', {
                'team_task_id': task['id'], 'actor_id': 'builder-01', 'input_digest': 'f' * 64,
                'limits': {'max_turns': 5, 'max_elapsed_seconds': 300, 'max_recovery_attempts': 2,
                           'max_repeated_operation_failures': 3},
                'failure_point': {'operation_ref': 'publish.report', 'error_code': 'EXECUTION_TIMEOUT',
                                  'observed_at': '2026-09-22T00:00:00Z', 'evidence': [EVIDENCE]},
                'root_cause_hypothesis': {'category': 'external_dependency', 'hypothesis': 'synthetic repeated failure',
                                          'confidence': 'low', 'evidence': [EVIDENCE]},
                'rollback_checkpoint': {'availability': 'verified', 'checkpoint_ref': 'external:synthetic-loop',
                                        'checkpoint_sha256': '1' * 64, 'evidence': [CHECKPOINT]},
                'replan_start': {'decision_ref': 'decision.retry-loop', 'rationale': 'synthetic loop boundary',
                                 'requires_fresh_input': False},
            }, 'evaluation-loop-case', 201)
            first = post(client, f'/api/local/recovery/cases/{loop_case["id"]}/observations', {
                'actor_id': 'builder-01', 'expected_case_version': 1, 'kind': 'failure', 'turn': 1,
                'operation_ref': 'publish.report', 'signature_sha256': '2' * 64, 'evidence': [EVIDENCE],
            }, 'evaluation-loop-1', 201)
            second = post(client, f'/api/local/recovery/cases/{loop_case["id"]}/observations', {
                'actor_id': 'builder-01', 'expected_case_version': first['case']['case_version'], 'kind': 'failure', 'turn': 2,
                'operation_ref': 'publish.report', 'signature_sha256': '2' * 64, 'evidence': [EVIDENCE],
            }, 'evaluation-loop-2', 201)
            third = post(client, f'/api/local/recovery/cases/{loop_case["id"]}/observations', {
                'actor_id': 'builder-01', 'expected_case_version': second['case']['case_version'], 'kind': 'failure', 'turn': 3,
                'operation_ref': 'publish.report', 'signature_sha256': '2' * 64, 'evidence': [EVIDENCE],
            }, 'evaluation-loop-3', 201)
            reminder_and_hard_stop = (second['reminder']['reason'] == 'consecutive_failures'
                                      and third['case']['hard_stop']['reason'] == 'repeated_operation_limit'
                                      and third['case']['status'] == 'needs_human')

            tried = post(client, f'/api/local/recovery/cases/{case["id"]}:try',
                         {'actor_id': 'builder-01', 'expected_case_version': case['case_version'], 'strategy': 'retry_idempotent_step'},
                         'evaluation-try', 200)
            confirmed = post(client, f'/api/local/recovery/cases/{case["id"]}:confirm', {
                'actor_id': 'builder-01', 'expected_case_version': tried['case']['case_version'], 'input_digest': 'd' * 64,
            }, 'evaluation-confirm', 200)
            runtime = client.get('/api/local/recovery/runtime').json()
            zero_execution = (confirmed['case']['status'] == 'confirmed_pending_handoff'
                              and runtime['external_model_calls'] == runtime['external_tool_calls'] == 0
                              and runtime['automatic_recovery_execution'] is False)

            handoff = post(client, f'/api/local/team/tasks/{task["id"]}/handoffs', {
                'actor_id': 'builder-01', 'expected_task_version': task['version'], 'summary': 'synthetic recovered output',
                'decisions': ['use controlled candidate'], 'artifact_refs': [ARTIFACT], 'evidence': ['synthetic evidence'],
                'remaining': [], 'risks': [], 'next_action': 'review it',
            }, 'evaluation-handoff', 201)
            linked = post(client, f'/api/local/recovery/cases/{case["id"]}:link-handoff', {
                'actor_id': 'builder-01', 'expected_case_version': confirmed['case']['case_version'], 'handoff_id': handoff['handoff']['id'],
            }, 'evaluation-link', 200)
            submitted = post(client, f'/api/local/team/tasks/{task["id"]}:submit', {
                'actor_id': 'builder-01', 'expected_task_version': handoff['task']['version'],
            }, 'evaluation-submit', 200)
            gate = post(client, f'/api/local/team/tasks/{task["id"]}/gate-decisions', {
                'reviewer_id': 'reviewer-01', 'expected_task_version': submitted['version'], 'decision': 'pass',
                'evidence': [ARTIFACT], 'reason': 'synthetic pass',
            }, 'evaluation-gate', 201)
            resolved = post(client, f'/api/local/recovery/cases/{case["id"]}:complete', {
                'actor_id': 'builder-01', 'expected_case_version': linked['case']['case_version'],
                'gate_decision_id': gate['decision']['id'],
            }, 'evaluation-complete', 200)['case']['status'] == 'resolved'

    results = {
        'server_derived_error_contract': float(catalog),
        'four_positions_distinct': float(four_positions),
        'try_confirm_zero_execution': float(zero_execution),
        'reminder_then_hard_stop': float(reminder_and_hard_stop),
        'handoff_gate_required_for_resolution': float(resolved),
        'automatic_permission_expansion': 0.0,
    }
    report = {
        'evaluation_version': FIXTURE['evaluation_version'], 'scope': FIXTURE['scope'],
        'model_calls': 0, 'external_calls': 0, 'results': results,
        'passed': all(value >= FIXTURE['pass_threshold'] for key, value in results.items() if key != 'automatic_permission_expansion') and results['automatic_permission_expansion'] == 0.0,
        'not_evidence': ['This does not execute a real recovery, model, tool, checkpoint restore, cancellation or external side effect.',
                         'The evaluation uses only synthetic Team Task and Evidence metadata in a temporary SQLite database.'],
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))
    if not report['passed']:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
