"""HA-0060: real HTTP + isolated SQLite; no Provider, daemon or live service."""
import json
from datetime import timedelta

import pytest
from fastapi.testclient import TestClient
from jsonschema import Draft202012Validator

from backend.analysis import Problem
from backend.app import create_app
from backend.team_coordination import iso_now


ACTOR = 'builder-60'
ROUTES = {
    'sessions': '/api/local/team/sessions',
    'tasks': '/api/local/team/tasks',
    'inbox': '/api/local/team/inbox',
    'recovery': '/api/local/recovery/cases',
}


def post(client, path, body, key, status=201):
    response = client.post('/api/local/' + path, json=body, headers={'Idempotency-Key': key})
    assert response.status_code == status, response.text
    return response.json()


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.delenv('HARNESS_AGENT_RUNTIME', raising=False)
    with TestClient(create_app(tmp_path / 'list-errors.db', False), base_url='http://127.0.0.1',
                    raise_server_exceptions=False) as value:
        def forbidden(*args, **kwargs):
            raise AssertionError('Metadata lists must not resolve credentials or call a Provider')
        value.app.state.service.agent_runtime.credentials.resolve = forbidden
        value.app.state.service.agent_runtime.adapters.require = forbidden
        post(value, 'team/workspaces/ws_local/agents', {
            'actor_id': 'local_admin', 'workspace_id': 'ws_local', 'id': ACTOR,
            'kind': 'agent', 'display_name': 'List test builder', 'clearance': 'Restricted',
        }, 'actor')
        yield value


def seed(client, suffix='one'):
    channel = 'ch_lists60_' + suffix
    post(client, 'team/workspaces/ws_local/channels', {
        'actor_id': 'local_admin', 'id': channel, 'title': 'List test ' + suffix,
        'data_class': 'Restricted',
    }, 'channel-' + suffix)
    post(client, 'team/channels/' + channel + '/memberships', {
        'actor_id': 'local_admin', 'agent_id': ACTOR, 'roles': ['contributor'],
    }, 'member-' + suffix)
    task = post(client, 'team/tasks', {
        'workspace_id': 'ws_local', 'channel_id': channel, 'thread_id': 'thread-' + suffix,
        'creator_id': 'local_admin', 'title': 'List test task ' + suffix,
        'objective': 'Verify metadata visibility and errors.', 'requirements': ['R1: retain evidence'],
        'scope': {'allowed_paths': ['tests/'], 'forbidden_paths': ['secrets/'], 'resource_refs': ['repo:local']},
        'stop_conditions': ['Stop on scope changes.'],
        'gate': {'reviewer_id': 'local_admin', 'checks': ['Verify evidence.'],
                 'evidence_requirements': ['test log'], 'on_reject': 'return builder'},
        'parent_task_id': None,
    }, 'task-' + suffix)
    task = post(client, 'team/tasks/' + task['id'] + ':claim', {
        'actor_id': ACTOR, 'lease_seconds': 300,
    }, 'claim-' + suffix, 200)
    case = post(client, 'recovery/cases', {
        'team_task_id': task['id'], 'actor_id': ACTOR, 'input_digest': 'd' * 64,
        'limits': {'max_turns': 5, 'max_elapsed_seconds': 300, 'max_recovery_attempts': 2,
                   'max_repeated_operation_failures': 3},
        'failure_point': {'operation_ref': 'publish.report', 'error_code': 'EXECUTION_TIMEOUT',
                          'observed_at': iso_now().isoformat().replace('+00:00', 'Z'),
                          'evidence': [{'kind': 'log', 'ref': 'logs/check.log', 'sha256': 'a' * 64}]},
        'root_cause_hypothesis': {'category': 'external_dependency', 'hypothesis': 'Unverified timeout.',
                                  'confidence': 'low',
                                  'evidence': [{'kind': 'log', 'ref': 'logs/check.log', 'sha256': 'a' * 64}]},
        'rollback_checkpoint': {'availability': 'verified', 'checkpoint_ref': 'external:checkpoint',
                                'checkpoint_sha256': 'e' * 64,
                                'evidence': [{'kind': 'checkpoint', 'ref': 'checkpoints/check.json', 'sha256': 'b' * 64}]},
        'replan_start': {'decision_ref': 'decision.retry', 'rationale': 'Reconsider the failed step.',
                         'requires_fresh_input': False},
    }, 'case-' + suffix)
    session = post(client, 'team/sessions', {
        'actor_id': ACTOR, 'workspace_id': 'ws_local', 'channel_id': channel,
    }, 'session-' + suffix)['session']
    item = post(client, 'team/attention/items', {
        'actor_id': 'local_admin', 'workspace_id': 'ws_local', 'channel_id': channel,
        'thread_id': 'thread-' + suffix, 'source_ref': 'source:message-' + suffix,
        'target_agent_id': ACTOR, 'kind': 'direct_mention',
    }, 'attention-' + suffix)['item']
    return {'channel': channel, 'sessions': session, 'tasks': task, 'recovery': case, 'inbox': item}


def read(client, route, actor=ACTOR, **params):
    return client.get(ROUTES[route], params={'actor_id': actor, **params})


def error(response, status, code):
    assert response.status_code == status, response.text
    assert response.json()['error']['code'] == code
    assert 'items' not in response.json()


def ids(response, route):
    assert response.status_code == 200, response.text
    return [entry['item']['id'] if route == 'inbox' else entry['id'] for entry in response.json()['items']]


def update_doc(client, table, where, params, change):
    # Test-only corruption/lifecycle injection into this test's isolated database.
    with client.app.state.service.store.transaction() as db:
        doc = json.loads(db.execute(f'SELECT doc FROM {table} WHERE {where}', params).fetchone()['doc'])
        change(doc)
        db.execute(f'UPDATE {table} SET doc=? WHERE {where}', (json.dumps(doc), *params))
    return doc


@pytest.mark.parametrize('route', ROUTES)
def test_list_does_not_swallow_access_service_failure(client, monkeypatch, route):
    created = seed(client)
    assert ids(read(client, route), route) == [created[route]['id']]
    # Inside the real access function, not replacing the entire authorizer.
    def unavailable(*args, **kwargs):
        raise Problem('ACCESS_BACKEND_UNAVAILABLE', 'Access backend temporarily unavailable.', 503)
    monkeypatch.setattr(client.app.state.service.team_foundation, '_channel', unavailable)
    error(read(client, route), 503, 'ACCESS_BACKEND_UNAVAILABLE')


def test_snapshot_does_not_swallow_task_access_failure(client, monkeypatch):
    created = seed(client)
    def unavailable(*args, **kwargs):
        raise Problem('ACCESS_BACKEND_UNAVAILABLE', 'Access backend temporarily unavailable.', 503)
    monkeypatch.setattr(client.app.state.service.team_foundation, 'assert_task_access', unavailable)
    response = client.get('/api/local/team/sessions/' + created['sessions']['id'], params={'actor_id': ACTOR})
    error(response, 503, 'ACCESS_BACKEND_UNAVAILABLE')


@pytest.mark.parametrize('route', ROUTES)
@pytest.mark.parametrize('code,status', [
    ('TEAM_CHANNEL_ACCESS_DENIED', 503),
    ('UNEXPECTED_AUTHORIZATION_FAILURE', 403),
    ('UNEXPECTED_STATE_CONFLICT', 409),
])
def test_unknown_error_or_mismatched_status_is_not_invisibility(client, monkeypatch, route, code, status):
    seed(client)
    def failure(*args, **kwargs):
        raise Problem(code, 'Injected non-visibility failure.', status)
    monkeypatch.setattr(client.app.state.service.team_foundation, '_channel', failure)
    error(read(client, route), status, code)


@pytest.mark.parametrize('route', ROUTES)
@pytest.mark.parametrize('failure', ['sqlite', 'missing_status'])
def test_internal_access_corruption_remains_server_error(client, monkeypatch, route, failure):
    created = seed(client)
    if failure == 'sqlite':
        def database_failure(db, *args, **kwargs):
            db.execute('SELECT * FROM nonexistent_table_ha60')
        monkeypatch.setattr(client.app.state.service.team_foundation, '_channel', database_failure)
    else:
        update_doc(client, 'team_channel_memberships', 'channel_id=? AND agent_id=?',
                   (created['channel'], ACTOR), lambda doc: doc.pop('status'))
    response = read(client, route)
    assert response.status_code == 500, response.text
    assert 'items' not in response.text
    assert created[route]['id'] not in response.text


@pytest.mark.parametrize('route', ROUTES)
@pytest.mark.parametrize('transition', ['channel_revoked', 'channel_archived', 'clearance',
                                       'workspace_revoked', 'workspace_archived'])
def test_expected_current_invisibility_still_filters(client, route, transition):
    hidden, visible = seed(client, 'hidden'), seed(client, 'visible')
    assert set(ids(read(client, route), route)) == {hidden[route]['id'], visible[route]['id']}
    if transition == 'channel_revoked':
        update_doc(client, 'team_channel_memberships', 'channel_id=? AND agent_id=?',
                   (hidden['channel'], ACTOR), lambda doc: doc.update(status='revoked'))
    elif transition == 'channel_archived':
        update_doc(client, 'team_channels', 'id=?', (hidden['channel'],), lambda doc: doc.update(status='archived'))
    elif transition == 'clearance':
        update_doc(client, 'team_channels', 'id=?', (visible['channel'],), lambda doc: doc.update(data_class='Internal'))
        update_doc(client, 'team_workspace_memberships', 'workspace_id=? AND agent_id=?',
                   ('ws_local', ACTOR), lambda doc: doc.update(clearance='Internal'))
    elif transition == 'workspace_revoked':
        update_doc(client, 'team_workspace_memberships', 'workspace_id=? AND agent_id=?',
                   ('ws_local', ACTOR), lambda doc: doc.update(status='revoked'))
    else:
        update_doc(client, 'team_workspaces', 'id=?', ('ws_local',), lambda doc: doc.update(status='archived'))
    result = read(client, route)
    expected = [] if transition.startswith('workspace_') else [visible[route]['id']]
    assert ids(result, route) == expected
    assert hidden[route]['id'] not in result.text
    if route == 'sessions':
        explicit = read(client, route, channel_id=hidden['channel'])
        assert explicit.status_code in {403, 409} and 'items' not in explicit.json()


@pytest.mark.parametrize('route', ROUTES)
@pytest.mark.parametrize('populated', [False, True])
def test_actor_errors_do_not_depend_on_list_contents(client, route, populated):
    if populated:
        seed(client)
    error(client.get(ROUTES[route]), 422, 'VALIDATION_ERROR')
    error(read(client, route, actor='missing-60'), 404, 'TEAM_AGENT_NOT_FOUND')
    update_doc(client, 'team_agent_identities', 'id=?', (ACTOR,), lambda doc: doc.update(status='suspended'))
    error(read(client, route), 403, 'TEAM_AGENT_SUSPENDED')


@pytest.mark.parametrize('route', ROUTES)
def test_list_roundtrip_schema_scope_and_order(client, route):
    assert ids(read(client, route), route) == []
    first, second = seed(client, 'first'), seed(client, 'second')
    result = read(client, route)
    expected = [first[route]['id'], second[route]['id']]
    if route != 'inbox':
        expected.reverse()
        assert ids(result, route) == expected
    else:
        # Inbox is priority/sequence/ID ordered, not reverse creation order.
        assert ids(result, route) == sorted(expected)
    runtime = result.json()['runtime']
    assert runtime['external_model_calls'] == runtime['external_tool_calls'] == 0
    assert runtime['agent_runtime'] == 'not_connected'
    document = client.get('/openapi.json').json()
    schema = document['paths'][ROUTES[route]]['get']['responses']['200']['content']['application/json']['schema']
    validator = Draft202012Validator({**document, **schema})
    validator.validate(result.json())
    assert not validator.is_valid({**result.json(), 'unexpected': True})
    if route in {'sessions', 'inbox'}:
        assert ids(read(client, route, actor='local_admin'), route) == []
    else:
        # Tasks/cases are channel-visible, not owner-only.
        assert set(ids(read(client, route, actor='local_admin'), route)) == set(expected)


@pytest.mark.parametrize('route,table,code', [
    ('sessions', 'team_sessions', 'TEAM_SESSION_SCOPE_INVALID'),
    ('tasks', 'team_tasks', 'TEAM_TASK_SCOPE_INVALID'),
    ('inbox', 'team_attention_items', 'TEAM_ATTENTION_SCOPE_INVALID'),
    ('recovery', 'team_tasks', 'TEAM_TASK_SCOPE_INVALID'),
])
def test_scope_corruption_is_explicit_error(client, route, table, code):
    created = seed(client)
    ident = created['tasks' if route == 'recovery' else route]['id']
    update_doc(client, table, 'id=?', (ident,), lambda doc: doc.update(workspace_id='ws_other60'))
    error(read(client, route), 409, code)


@pytest.mark.parametrize('route', ROUTES)
def test_missing_channel_reference_is_not_empty_list(client, route):
    created = seed(client)
    table = {'sessions': 'team_sessions', 'tasks': 'team_tasks',
             'inbox': 'team_attention_items', 'recovery': 'team_tasks'}[route]
    ident = created['tasks' if route == 'recovery' else route]['id']
    # Corrupt the JSON reference without bypassing real SQLite FK constraints.
    update_doc(client, table, 'id=?', (ident,), lambda doc: doc.update(channel_id='ch_missing60'))
    error(read(client, route), 404, 'TEAM_CHANNEL_NOT_FOUND')


@pytest.mark.parametrize('route,table,field,code', [
    ('sessions', 'team_sessions', 'agent_id', 'TEAM_SESSION_OWNER_FORBIDDEN'),
    ('inbox', 'team_attention_items', 'target_agent_id', 'TEAM_ATTENTION_TARGET_FORBIDDEN'),
])
def test_owner_column_document_mismatch_is_not_filtered(client, route, table, field, code):
    created = seed(client)
    update_doc(client, table, 'id=?', (created[route]['id'],), lambda doc: doc.update({field: 'local_admin'}))
    error(read(client, route), 403, code)


@pytest.mark.parametrize('route', ROUTES)
def test_legacy_task_exception_only_applies_to_task_checks(client, monkeypatch, route):
    seed(client)
    def legacy(*args, **kwargs):
        raise Problem('TEAM_TASK_LEGACY_UNBOUND', 'Legacy task.', 409)
    monkeypatch.setattr(client.app.state.service.team_foundation, '_channel', legacy)
    if route in {'tasks', 'recovery'}:
        assert ids(read(client, route), route) == []
    else:
        error(read(client, route), 409, 'TEAM_TASK_LEGACY_UNBOUND')


def snapshot_tables(client, tables):
    with client.app.state.service.store.transaction() as db:
        return {table: [tuple(row) for row in db.execute('SELECT * FROM ' + table + ' ORDER BY rowid')]
                for table in tables}


@pytest.mark.parametrize('route', ['inbox', 'recovery'])
def test_read_failure_rolls_back_lazy_expiry(client, monkeypatch, route):
    created = seed(client)
    expired = (iso_now() - timedelta(seconds=1)).isoformat().replace('+00:00', 'Z')
    if route == 'recovery':
        update_doc(client, 'recovery_cases', 'id=?', (created[route]['id'],),
                   lambda doc: doc.update(deadline_at=expired))
        update_doc(client, 'team_tasks', 'id=?', (created['tasks']['id'],),
                   lambda doc: doc['lease'].update(expires_at=expired))
        tables = ['recovery_cases', 'team_tasks']
    else:
        post(client, 'team/attention/items/' + created['inbox']['id'] + ':claim', {
            'actor_id': ACTOR, 'lease_seconds': 300,
        }, 'attention-claim', 200)
        update_doc(client, 'team_attention_items', 'id=?', (created['inbox']['id'],),
                   lambda doc: doc['lease'].update(expires_at=expired))
        tables = ['team_attention_items', 'team_attention_leases', 'team_attention_work_marks']
    before = snapshot_tables(client, tables)
    foundation = client.app.state.service.team_foundation
    original = foundation._channel
    def unavailable(*args, **kwargs):
        raise Problem('ACCESS_BACKEND_UNAVAILABLE', 'Access backend temporarily unavailable.', 503)
    monkeypatch.setattr(foundation, '_channel', unavailable)
    error(read(client, route), 503, 'ACCESS_BACKEND_UNAVAILABLE')
    assert snapshot_tables(client, tables) == before
    monkeypatch.setattr(foundation, '_channel', original)
    result = read(client, route)
    assert ids(result, route) == [created[route]['id']]
    if route == 'recovery':
        assert result.json()['items'][0]['hard_stop']['reason'] == 'elapsed_time_limit'
    else:
        assert result.json()['items'][0]['item']['status'] == 'pending'
    assert snapshot_tables(client, tables) != before


def test_failed_snapshot_does_not_retire_session_or_publish_handoff(client, monkeypatch):
    created = seed(client)
    tables = ['team_sessions', 'team_session_handoffs', 'idempotency']
    before = snapshot_tables(client, tables)
    def unavailable(*args, **kwargs):
        raise Problem('ACCESS_BACKEND_UNAVAILABLE', 'Access backend temporarily unavailable.', 503)
    monkeypatch.setattr(client.app.state.service.team_foundation, 'assert_task_access', unavailable)
    response = client.post('/api/local/team/sessions/' + created['sessions']['id'] + ':handoff', json={
        'actor_id': ACTOR, 'expected_session_version': 1, 'reason': 'manual_handoff',
    }, headers={'Idempotency-Key': 'failed-handoff'})
    error(response, 503, 'ACCESS_BACKEND_UNAVAILABLE')
    assert snapshot_tables(client, tables) == before
