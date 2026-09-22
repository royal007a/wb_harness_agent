import concurrent.futures
import copy
import json
from datetime import timedelta

import pytest
import yaml
from fastapi.testclient import TestClient
from jsonschema import Draft202012Validator

from backend.app import create_app
from backend.service import ROOT
from backend.team_coordination import iso_now


CREATE = {
    'channel_id': 'ch_harness_local',
    'thread_id': 'thread-demo-01',
    'title': '修复刷新重试逻辑',
    'objective': '保留兼容层，并确保同一批并发请求最多刷新一次。',
    'requirements': ['R1：保留旧接口兼容层。', 'R2：同一批并发请求最多触发一次 refresh。'],
    'scope': {'allowed_paths': ['internal/auth/'], 'forbidden_paths': ['db/'], 'resource_refs': ['repo:local']},
    'stop_conditions': ['需要变更公开接口时停止并转人工。'],
    'gate': {
        'reviewer_id': 'reviewer-01',
        'checks': ['运行兼容性与并发刷新回归。'],
        'evidence_requirements': ['对应提交和检查记录。'],
        'on_reject': '带问题与证据退回 builder-01。',
    },
    'parent_task_id': None,
}
ARTIFACT = {'kind': 'test_result', 'ref': 'checks/refresh.log', 'sha256': 'a' * 64}


@pytest.fixture
def client(tmp_path):
    with TestClient(create_app(tmp_path / 'team.db', False), base_url='http://127.0.0.1') as value:
        yield value


def create_task(client, key='team-create', **changes):
    response = client.post('/api/local/team/tasks', json={**CREATE, **changes}, headers={'Idempotency-Key': key})
    assert response.status_code == 201, response.text
    return response.json()


def claim(client, task_id, key='team-claim', actor='builder-01'):
    response = client.post(f'/api/local/team/tasks/{task_id}:claim', json={
        'actor_id': actor, 'lease_seconds': 300,
    }, headers={'Idempotency-Key': key})
    assert response.status_code == 200, response.text
    return response.json()


def handoff(client, task, key='team-handoff', actor='builder-01'):
    response = client.post(f'/api/local/team/tasks/{task["id"]}/handoffs', json={
        'actor_id': actor, 'expected_task_version': task['version'], 'summary': '兼容层已保留，并发断言已覆盖。',
        'decisions': ['保留旧接口兼容层。'], 'artifact_refs': [ARTIFACT],
        'evidence': ['兼容性、并发回归均已执行。'], 'remaining': [],
        'risks': ['尚未进行生产环境验证。'], 'next_action': '请 reviewer-01 进行 Gate 审核。',
    }, headers={'Idempotency-Key': key})
    assert response.status_code == 201, response.text
    return response.json()


def submit(client, task, key='team-submit', actor='builder-01'):
    response = client.post(f'/api/local/team/tasks/{task["id"]}:submit', json={
        'actor_id': actor, 'expected_task_version': task['version'],
    }, headers={'Idempotency-Key': key})
    assert response.status_code == 200, response.text
    return response.json()


def decide(client, task, decision, key='team-gate', reviewer='reviewer-01'):
    response = client.post(f'/api/local/team/tasks/{task["id"]}/gate-decisions', json={
        'reviewer_id': reviewer, 'expected_task_version': task['version'], 'decision': decision,
        'evidence': [ARTIFACT], 'reason': '按 Gate 的已登记检查结果裁决。',
    }, headers={'Idempotency-Key': key})
    assert response.status_code == 201, response.text
    return response.json()


def test_team_task_freezes_contract_and_idempotent_create(client):
    first = create_task(client)
    replay = client.post('/api/local/team/tasks', json=CREATE, headers={'Idempotency-Key': 'team-create'})
    assert replay.status_code == 201 and replay.json() == first
    changed = client.post('/api/local/team/tasks', json={**CREATE, 'title': '其他任务'},
                          headers={'Idempotency-Key': 'team-create'})
    assert changed.status_code == 409
    assert first['schema_version'] == 'team-task@1'
    assert len(first['requirements_digest']) == len(first['gate_digest']) == 64
    assert first['status'] == 'todo' and first['lease'] is None
    listed = client.get('/api/local/team/tasks').json()
    assert [item['id'] for item in listed['items']] == [first['id']]
    assert listed['runtime']['agent_runtime'] == 'not_connected'


def test_atomic_claim_handoff_and_version_binding(client):
    task = create_task(client)

    def attempt(actor):
        return client.post(f'/api/local/team/tasks/{task["id"]}:claim', json={
            'actor_id': actor, 'lease_seconds': 300,
        }, headers={'Idempotency-Key': 'claim-' + actor})

    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(attempt, ['builder-01', 'builder-02']))
    assert sorted(result.status_code for result in results) == [200, 409]
    claimed = next(result.json() for result in results if result.status_code == 200)
    assert claimed['status'] == 'in_progress' and claimed['lease']['claimant_id'] == claimed['assignee_id']

    stale = client.post(f'/api/local/team/tasks/{task["id"]}/handoffs', json={
        'actor_id': claimed['assignee_id'], 'expected_task_version': 1, 'summary': 'stale', 'decisions': [],
        'artifact_refs': [], 'evidence': [], 'remaining': [], 'risks': [], 'next_action': 'retry',
    }, headers={'Idempotency-Key': 'stale-handoff'})
    assert stale.status_code == 409 and stale.json()['error']['code'] == 'TEAM_TASK_VERSION_CONFLICT'

    result = handoff(client, claimed, actor=claimed['assignee_id'])
    assert result['handoff']['task_version'] == claimed['version']
    assert result['handoff']['requirements_digest'] == claimed['requirements_digest']
    assert result['handoff']['gate_digest'] == claimed['gate_digest']
    assert result['task']['version'] == claimed['version'] + 1
    detail = client.get('/api/local/team/tasks/' + task['id']).json()
    assert len(detail['handoffs']) == 1 and detail['handoffs'][0] == result['handoff']


def test_parent_child_gate_three_exits_and_reject_reclaim(client):
    parent = create_task(client, key='parent-create', title='父任务')
    child = create_task(client, key='child-create', parent_task_id=parent['id'], title='子任务')
    parent_claim = claim(client, parent['id'], key='parent-claim')
    parent_handoff = handoff(client, parent_claim, key='parent-handoff')['task']
    blocked = client.post(f'/api/local/team/tasks/{parent["id"]}:submit', json={
        'actor_id': 'builder-01', 'expected_task_version': parent_handoff['version'],
    }, headers={'Idempotency-Key': 'parent-submit-blocked'})
    assert blocked.status_code == 409 and blocked.json()['error']['code'] == 'TEAM_TASK_CHILDREN_OPEN'

    child_claim = claim(client, child['id'], key='child-claim')
    child_handoff = handoff(client, child_claim, key='child-handoff')['task']
    child_review = submit(client, child_handoff, key='child-submit')
    child_done = decide(client, child_review, 'pass', key='child-pass')
    assert child_done['task']['status'] == 'done'

    parent_review = submit(client, parent_handoff, key='parent-submit')
    needs_human = decide(client, parent_review, 'needs_human', key='parent-needs-human')
    assert needs_human['task']['status'] == 'in_review'
    stale_pass = client.post(f'/api/local/team/tasks/{parent["id"]}/gate-decisions', json={
        'reviewer_id': 'reviewer-01', 'expected_task_version': parent_review['version'], 'decision': 'pass',
        'evidence': [ARTIFACT], 'reason': 'stale',
    }, headers={'Idempotency-Key': 'parent-stale-pass'})
    assert stale_pass.status_code == 409 and stale_pass.json()['error']['code'] == 'TEAM_TASK_VERSION_CONFLICT'
    parent_done = decide(client, needs_human['task'], 'pass', key='parent-pass')
    assert parent_done['task']['status'] == 'done'

    rejected = create_task(client, key='reject-create', title='需要返工')
    rejected_claim = claim(client, rejected['id'], key='reject-claim')
    rejected_review = submit(client, handoff(client, rejected_claim, key='reject-handoff')['task'], key='reject-submit')
    rejected_result = decide(client, rejected_review, 'reject', key='reject-decision')
    assert rejected_result['task']['status'] == 'in_progress' and rejected_result['task']['lease'] is None
    other = client.post(f'/api/local/team/tasks/{rejected["id"]}:claim', json={
        'actor_id': 'builder-02', 'lease_seconds': 300,
    }, headers={'Idempotency-Key': 'reject-other'})
    assert other.status_code == 409
    reclaimed = claim(client, rejected['id'], key='reject-reclaim')
    assert reclaimed['assignee_id'] == 'builder-01' and reclaimed['lease'] is not None


def test_team_state_persists_across_restart_and_openapi_is_explicit(tmp_path):
    database = tmp_path / 'restart-team.db'
    with TestClient(create_app(database, False), base_url='http://127.0.0.1') as local:
        task = create_task(local, key='restart-create')
        claimed = claim(local, task['id'], key='restart-claim')
        expected = handoff(local, claimed, key='restart-handoff')
        assert expected['task']['handoff_count'] == 1
    with TestClient(create_app(database, False), base_url='http://127.0.0.1') as restarted:
        detail = restarted.get('/api/local/team/tasks/' + task['id']).json()
        assert detail['task']['handoff_count'] == 1
        assert detail['handoffs'][0]['artifact_refs'] == [ARTIFACT]
        assert detail['runtime']['external_model_calls'] == detail['runtime']['external_tool_calls'] == 0
        contract = json.load(open(ROOT / 'specs/v1/team-coordination.schema.json'))
        validator = Draft202012Validator({'$ref': '#/$defs/team_task_detail', '$defs': contract['$defs']})
        assert validator.is_valid(detail)
        static = yaml.safe_load((ROOT / 'specs/v1/openapi.yaml').read_text())
        runtime_paths = restarted.app.openapi()['paths']
        pairs = {
            '/local/team/runtime': '/api/local/team/runtime',
            '/local/team/tasks': '/api/local/team/tasks',
            '/local/team/tasks/{taskId}': '/api/local/team/tasks/{task_id}',
            '/local/team/tasks/{taskId}:claim': '/api/local/team/tasks/{task_id}:claim',
            '/local/team/tasks/{taskId}/handoffs': '/api/local/team/tasks/{task_id}/handoffs',
            '/local/team/tasks/{taskId}:submit': '/api/local/team/tasks/{task_id}:submit',
            '/local/team/tasks/{taskId}:close': '/api/local/team/tasks/{task_id}:close',
            '/local/team/tasks/{taskId}/gate-decisions': '/api/local/team/tasks/{task_id}/gate-decisions',
        }
        for static_path, runtime_path in pairs.items():
            assert static_path in static['paths'] and runtime_path in runtime_paths
        assert runtime_paths['/api/local/team/tasks/{task_id}/handoffs']['post']['responses']['201']['content']['application/json']['schema'] == {
            '$ref': '#/components/schemas/handoff_result'
        }


def test_team_contract_rejects_unknown_fields_and_wrong_gate_reviewer(client):
    invalid = client.post('/api/local/team/tasks', json={**CREATE, 'workspace_id': 'not-accepted'},
                          headers={'Idempotency-Key': 'bad-team'})
    assert invalid.status_code == 422
    task = create_task(client, key='reviewer-create')
    claimed = claim(client, task['id'], key='reviewer-claim')
    review = submit(client, handoff(client, claimed, key='reviewer-handoff')['task'], key='reviewer-submit')
    forbidden = client.post(f'/api/local/team/tasks/{task["id"]}/gate-decisions', json={
        'reviewer_id': 'other-reviewer', 'expected_task_version': review['version'], 'decision': 'pass',
        'evidence': [ARTIFACT], 'reason': 'not allowed',
    }, headers={'Idempotency-Key': 'wrong-reviewer'})
    assert forbidden.status_code == 403 and forbidden.json()['error']['code'] == 'TEAM_TASK_GATE_FORBIDDEN'


def test_team_contract_rejects_credential_shaped_collaboration_content(client):
    rejected = client.post('/api/local/team/tasks', json={
        **CREATE, 'objective': 'password=should-not-be-persisted',
    }, headers={'Idempotency-Key': 'sensitive-team'})
    assert rejected.status_code == 422
    assert rejected.json()['error']['code'] == 'SENSITIVE_INPUT_REJECTED'


def test_expired_lease_releases_task_and_closed_child_no_longer_blocks_parent(client):
    parent = create_task(client, key='close-parent', title='父项')
    child = create_task(client, key='close-child', parent_task_id=parent['id'], title='取消的子项')
    claim(client, child['id'], key='close-child-claim')
    team = client.app.state.service.team
    with client.app.state.service.store.transaction() as db:
        stored = team._row_task(db, child['id'])
        stored['lease']['expires_at'] = (iso_now() - timedelta(seconds=1)).isoformat().replace('+00:00', 'Z')
        team._write_task(db, stored)
    released = client.get(f'/api/local/team/tasks/{child["id"]}').json()['task']
    assert released['status'] == 'todo' and released['assignee_id'] is None and released['lease'] is None
    reclaimed = claim(client, child['id'], key='close-child-reclaim', actor='builder-02')
    closed = client.post(f'/api/local/team/tasks/{child["id"]}:close', json={
        'actor_id': 'builder-02', 'expected_task_version': reclaimed['version'], 'reason': '父任务不再需要该验证。',
    }, headers={'Idempotency-Key': 'close-child-close'})
    assert closed.status_code == 200, closed.text
    closed_task = closed.json()
    assert closed_task['status'] == 'closed' and closed_task['closure']['actor_id'] == 'builder-02'
    parent_claim = claim(client, parent['id'], key='close-parent-claim')
    parent_handoff = handoff(client, parent_claim, key='close-parent-handoff')['task']
    review = submit(client, parent_handoff, key='close-parent-submit')
    assert review['status'] == 'in_review'
