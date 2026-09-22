import copy
import json

import pytest
import yaml
from fastapi.testclient import TestClient
from jsonschema import Draft202012Validator

from backend.app import create_app
from backend.team_coordination import iso_now


TASK = {
    'channel_id': 'ch_recovery_local', 'thread_id': 'thread-recovery-01', 'title': '恢复受限流程',
    'objective': '保留既有交接与验收约束。', 'requirements': ['R1：结果必须可追溯。'],
    'scope': {'allowed_paths': ['internal/'], 'forbidden_paths': ['db/'], 'resource_refs': ['repo:local']},
    'stop_conditions': ['需要扩大权限时停止并转人工。'],
    'gate': {'reviewer_id': 'reviewer-01', 'checks': ['核对结果和证据。'],
             'evidence_requirements': ['提交和检查记录。'], 'on_reject': '退回 builder-01。'},
    'parent_task_id': None,
}
SHA = 'a' * 64
EVIDENCE = {'kind': 'log', 'ref': 'logs/recovery.log', 'sha256': SHA}
CHECKPOINT_EVIDENCE = {'kind': 'checkpoint', 'ref': 'checkpoints/demo.json', 'sha256': 'b' * 64}
ARTIFACT = {'kind': 'test_result', 'ref': 'checks/recovery.log', 'sha256': 'c' * 64}


@pytest.fixture
def client(tmp_path):
    with TestClient(create_app(tmp_path / 'recovery.db', False), base_url='http://127.0.0.1') as value:
        yield value


def task_and_claim(client, suffix='one'):
    response = client.post('/api/local/team/tasks', json=TASK, headers={'Idempotency-Key': 'task-' + suffix})
    assert response.status_code == 201, response.text
    task = response.json()
    response = client.post(f'/api/local/team/tasks/{task["id"]}:claim', json={
        'actor_id': 'builder-01', 'lease_seconds': 300,
    }, headers={'Idempotency-Key': 'claim-' + suffix})
    assert response.status_code == 200, response.text
    return response.json()


def recovery_body(task, **changes):
    body = {
        'team_task_id': task['id'], 'actor_id': 'builder-01', 'input_digest': 'd' * 64,
        'limits': {'max_turns': 5, 'max_elapsed_seconds': 300, 'max_recovery_attempts': 2,
                   'max_repeated_operation_failures': 3},
        'failure_point': {'operation_ref': 'publish.report', 'error_code': 'EXECUTION_TIMEOUT',
                          'observed_at': iso_now().isoformat().replace('+00:00', 'Z'), 'evidence': [EVIDENCE]},
        'root_cause_hypothesis': {'category': 'external_dependency', 'hypothesis': '下游短暂不可用，尚未被证实。',
                                  'confidence': 'low', 'evidence': [EVIDENCE]},
        'rollback_checkpoint': {'availability': 'verified', 'checkpoint_ref': 'external:checkpoint-demo',
                                'checkpoint_sha256': 'e' * 64, 'evidence': [CHECKPOINT_EVIDENCE]},
        'replan_start': {'decision_ref': 'decision.retry-publish', 'rationale': '只从发布决策重新选择路径。',
                         'requires_fresh_input': False},
    }
    body.update(changes)
    return body


def create_case(client, task, suffix='one', **changes):
    response = client.post('/api/local/recovery/cases', json=recovery_body(task, **changes),
                           headers={'Idempotency-Key': 'case-' + suffix})
    assert response.status_code == 201, response.text
    return response.json()


def try_candidate(client, case, suffix='one'):
    response = client.post(f'/api/local/recovery/cases/{case["id"]}:try', json={
        'actor_id': 'builder-01', 'expected_case_version': case['case_version'], 'strategy': 'retry_idempotent_step',
    }, headers={'Idempotency-Key': 'try-' + suffix})
    assert response.status_code == 200, response.text
    return response.json()


def test_error_contract_four_positions_and_runtime_are_explicit(client):
    task = task_and_claim(client)
    case = create_case(client, task)

    assert case['error_contract'] == {
        'schema_version': 'error-contract@1', 'error_code': 'EXECUTION_TIMEOUT', 'retryable': True,
        'recommended_next_action': 'retry_after_confirm',
        'required_evidence': ['failure_event', 'operation_log', 'task_contract', 'input_digest', 'budget_snapshot'],
    }
    assert case['failure_point']['operation_ref'] == 'publish.report'
    assert case['root_cause_hypothesis']['hypothesis'].endswith('尚未被证实。')
    assert case['rollback_checkpoint']['checkpoint_ref'] == 'external:checkpoint-demo'
    assert case['replan_start']['decision_ref'] == 'decision.retry-publish'
    assert case['permission_snapshot']['allow_tools'] == []
    assert case['permission_snapshot']['deny_capabilities'] == ['network', 'package_install', 'external_write', 'host_path', 'secret']

    runtime = client.get('/api/local/recovery/runtime').json()
    assert runtime['agent_runtime'] == 'not_connected'
    assert runtime['external_model_calls'] == runtime['external_tool_calls'] == 0
    assert runtime['automatic_recovery_execution'] is False


def test_try_confirm_requires_team_handoff_and_gate_before_resolution(client):
    task = task_and_claim(client)
    case = create_case(client, task)
    tried = try_candidate(client, case)
    assert tried['attempt']['status'] == 'proposed'
    assert tried['case']['status'] == 'open'
    assert client.get('/api/local/team/tasks/' + task['id']).json()['task']['version'] == task['version']

    confirmed = client.post(f'/api/local/recovery/cases/{case["id"]}:confirm', json={
        'actor_id': 'builder-01', 'expected_case_version': tried['case']['case_version'], 'input_digest': 'd' * 64,
    }, headers={'Idempotency-Key': 'confirm-one'})
    assert confirmed.status_code == 200, confirmed.text
    confirmed = confirmed.json()
    assert confirmed['attempt']['status'] == 'confirmed'
    assert confirmed['case']['status'] == 'confirmed_pending_handoff'

    premature = client.post(f'/api/local/recovery/cases/{case["id"]}:complete', json={
        'actor_id': 'builder-01', 'expected_case_version': confirmed['case']['case_version'], 'gate_decision_id': 'gate_' + 'f' * 32,
    }, headers={'Idempotency-Key': 'premature'})
    assert premature.status_code == 409 and premature.json()['error']['code'] == 'RECOVERY_GATE_REQUIRED'

    handoff = client.post(f'/api/local/team/tasks/{task["id"]}/handoffs', json={
        'actor_id': 'builder-01', 'expected_task_version': task['version'], 'summary': '恢复路径已验证，但仍需要 Gate。',
        'decisions': ['使用受限恢复候选。'], 'artifact_refs': [ARTIFACT], 'evidence': ['检查记录已附。'],
        'remaining': [], 'risks': ['未扩展工具权限。'], 'next_action': '请 reviewer-01 审核。',
    }, headers={'Idempotency-Key': 'handoff-one'})
    assert handoff.status_code == 201, handoff.text
    handoff = handoff.json()

    linked = client.post(f'/api/local/recovery/cases/{case["id"]}:link-handoff', json={
        'actor_id': 'builder-01', 'expected_case_version': confirmed['case']['case_version'], 'handoff_id': handoff['handoff']['id'],
    }, headers={'Idempotency-Key': 'link-one'})
    assert linked.status_code == 200, linked.text
    linked = linked.json()
    assert linked['case']['status'] == 'recovery_reported'

    submitted = client.post(f'/api/local/team/tasks/{task["id"]}:submit', json={
        'actor_id': 'builder-01', 'expected_task_version': handoff['task']['version'],
    }, headers={'Idempotency-Key': 'submit-one'})
    assert submitted.status_code == 200, submitted.text
    submitted = submitted.json()
    decision = client.post(f'/api/local/team/tasks/{task["id"]}/gate-decisions', json={
        'reviewer_id': 'reviewer-01', 'expected_task_version': submitted['version'], 'decision': 'pass',
        'evidence': [ARTIFACT], 'reason': 'Gate 检查通过。',
    }, headers={'Idempotency-Key': 'gate-one'})
    assert decision.status_code == 201, decision.text
    decision = decision.json()

    complete = client.post(f'/api/local/recovery/cases/{case["id"]}:complete', json={
        'actor_id': 'builder-01', 'expected_case_version': linked['case']['case_version'],
        'gate_decision_id': decision['decision']['id'],
    }, headers={'Idempotency-Key': 'complete-one'})
    assert complete.status_code == 200, complete.text
    assert complete.json()['case']['status'] == 'resolved'


def test_soft_reminder_then_hard_repeat_limit_and_cancel_stays_audit_only(client):
    task = task_and_claim(client, 'two')
    case = create_case(client, task, 'two')
    first = client.post(f'/api/local/recovery/cases/{case["id"]}/observations', json={
        'actor_id': 'builder-01', 'expected_case_version': 1, 'kind': 'failure', 'turn': 1,
        'operation_ref': 'publish.report', 'signature_sha256': 'f' * 64, 'evidence': [EVIDENCE],
    }, headers={'Idempotency-Key': 'obs-1'})
    assert first.status_code == 201 and first.json()['reminder'] is None
    second = client.post(f'/api/local/recovery/cases/{case["id"]}/observations', json={
        'actor_id': 'builder-01', 'expected_case_version': first.json()['case']['case_version'], 'kind': 'failure', 'turn': 2,
        'operation_ref': 'publish.report', 'signature_sha256': 'f' * 64, 'evidence': [EVIDENCE],
    }, headers={'Idempotency-Key': 'obs-2'})
    assert second.status_code == 201, second.text
    assert second.json()['reminder']['reason'] == 'consecutive_failures'
    third = client.post(f'/api/local/recovery/cases/{case["id"]}/observations', json={
        'actor_id': 'builder-01', 'expected_case_version': second.json()['case']['case_version'], 'kind': 'failure', 'turn': 3,
        'operation_ref': 'publish.report', 'signature_sha256': 'f' * 64, 'evidence': [EVIDENCE],
    }, headers={'Idempotency-Key': 'obs-3'})
    assert third.status_code == 201, third.text
    assert third.json()['case']['hard_stop']['reason'] == 'repeated_operation_limit'
    assert third.json()['case']['status'] == 'needs_human'

    task2 = task_and_claim(client, 'three')
    case2 = create_case(client, task2, 'three')
    tried = try_candidate(client, case2, 'three')
    cancelled = client.post(f'/api/local/recovery/cases/{case2["id"]}:cancel', json={
        'actor_id': 'builder-01', 'expected_case_version': tried['case']['case_version'], 'reason': '用户取消候选，不执行补救。',
    }, headers={'Idempotency-Key': 'cancel-three'})
    assert cancelled.status_code == 200, cancelled.text
    cancelled = cancelled.json()
    assert cancelled['attempt']['status'] == 'cancelled'
    assert cancelled['case']['hard_stop']['reason'] == 'cancelled'
    assert cancelled['case']['status'] == 'cancelled'

    no_progress = create_case(client, task2, 'no-progress', input_digest='8' * 64)
    first_no_progress = client.post(f'/api/local/recovery/cases/{no_progress["id"]}/observations', json={
        'actor_id': 'builder-01', 'expected_case_version': 1, 'kind': 'failure', 'turn': 1,
        'operation_ref': 'inspect.report', 'signature_sha256': '7' * 64, 'evidence': [EVIDENCE],
    }, headers={'Idempotency-Key': 'no-progress-1'})
    assert first_no_progress.status_code == 201
    second_no_progress = client.post(f'/api/local/recovery/cases/{no_progress["id"]}/observations', json={
        'actor_id': 'builder-01', 'expected_case_version': first_no_progress.json()['case']['case_version'], 'kind': 'failure', 'turn': 2,
        'operation_ref': 'publish.report', 'signature_sha256': '6' * 64, 'evidence': [EVIDENCE],
    }, headers={'Idempotency-Key': 'no-progress-2'})
    assert second_no_progress.status_code == 201, second_no_progress.text
    assert second_no_progress.json()['reminder']['reason'] == 'no_verifiable_progress'
    team_detail = client.get('/api/local/team/tasks/' + task2['id']).json()
    assert team_detail['task']['version'] == task2['version'] and team_detail['handoffs'] == []


def test_binding_changes_and_unavailable_checkpoint_are_rejected(client):
    task = task_and_claim(client, 'four')
    unavailable = create_case(client, task, 'four', rollback_checkpoint={
        'availability': 'unavailable', 'checkpoint_ref': None, 'checkpoint_sha256': None, 'evidence': [CHECKPOINT_EVIDENCE],
    })
    assert unavailable['status'] == 'open'  # timeout itself is retryable; rollback candidate is still forbidden.
    rollback = client.post(f'/api/local/recovery/cases/{unavailable["id"]}:try', json={
        'actor_id': 'builder-01', 'expected_case_version': 1, 'strategy': 'rollback_to_verified_checkpoint',
    }, headers={'Idempotency-Key': 'rollback-four'})
    assert rollback.status_code == 409 and rollback.json()['error']['code'] == 'RECOVERY_CHECKPOINT_UNAVAILABLE'

    tried = try_candidate(client, unavailable, 'four-retry')
    wrong_input = client.post(f'/api/local/recovery/cases/{unavailable["id"]}:confirm', json={
        'actor_id': 'builder-01', 'expected_case_version': tried['case']['case_version'], 'input_digest': '9' * 64,
    }, headers={'Idempotency-Key': 'wrong-input-four'})
    assert wrong_input.status_code == 409 and wrong_input.json()['error']['code'] == 'RECOVERY_INPUT_VERSION_CONFLICT'

    limited_task = task_and_claim(client, 'attempt-limit')
    limited = create_case(client, limited_task, 'attempt-limit', limits={
        'max_turns': 5, 'max_elapsed_seconds': 300, 'max_recovery_attempts': 1, 'max_repeated_operation_failures': 3,
    })
    first_attempt = try_candidate(client, limited, 'attempt-limit-one')
    blocked = client.post(f'/api/local/recovery/cases/{limited["id"]}:try', json={
        'actor_id': 'builder-01', 'expected_case_version': first_attempt['case']['case_version'], 'strategy': 'retry_idempotent_step',
    }, headers={'Idempotency-Key': 'attempt-limit-two'})
    assert blocked.status_code == 200, blocked.text
    assert blocked.json()['attempt'] is None
    assert blocked.json()['case']['hard_stop']['reason'] == 'recovery_attempt_limit'
    assert blocked.json()['case']['status'] == 'needs_human'


def test_recovery_case_and_cancel_audit_survive_restart(tmp_path):
    database = tmp_path / 'restart-recovery.db'
    with TestClient(create_app(database, False), base_url='http://127.0.0.1') as first:
        task = task_and_claim(first, 'restart')
        case = create_case(first, task, 'restart')
        tried = try_candidate(first, case, 'restart')
        cancelled = first.post(f'/api/local/recovery/cases/{case["id"]}:cancel', json={
            'actor_id': 'builder-01', 'expected_case_version': tried['case']['case_version'], 'reason': 'synthetic restart audit',
        }, headers={'Idempotency-Key': 'restart-cancel'})
        assert cancelled.status_code == 200, cancelled.text
    with TestClient(create_app(database, False), base_url='http://127.0.0.1') as second:
        detail = second.get(f'/api/local/recovery/cases/{case["id"]}')
        assert detail.status_code == 200, detail.text
        detail = detail.json()
        assert detail['case']['status'] == 'cancelled'
        assert detail['attempts'][-1]['status'] == 'cancelled'
        assert detail['cancel_audits'][-1]['reason'] == 'synthetic restart audit'


def test_openapi_and_recovery_schema_are_machine_valid(client):
    schema = json.loads((__import__('pathlib').Path(__file__).parents[1] / 'specs/v1/recovery-loop-guard.schema.json').read_text())
    Draft202012Validator.check_schema(schema)
    with open(__import__('pathlib').Path(__file__).parents[1] / 'specs/v1/openapi.yaml') as stream:
        source = yaml.safe_load(stream)
    expected = {
        '/local/recovery/runtime', '/local/recovery/cases', '/local/recovery/cases/{caseId}',
        '/local/recovery/cases/{caseId}/observations', '/local/recovery/cases/{caseId}:try',
        '/local/recovery/cases/{caseId}:confirm', '/local/recovery/cases/{caseId}:cancel',
        '/local/recovery/cases/{caseId}:link-handoff', '/local/recovery/cases/{caseId}:complete',
    }
    assert expected <= set(source['paths'])
