"""HTTP protocol-identity visibility; not authentication or real Agent execution."""
import json

import pytest
from fastapi.testclient import TestClient
from jsonschema import Draft202012Validator, FormatChecker

from backend.app import create_app
from backend.team_foundation import validate_contract


BASE = '/api/local/team'


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.delenv('HARNESS_AGENT_RUNTIME', raising=False)
    with TestClient(create_app(tmp_path / 'visibility.db', False), base_url='http://127.0.0.1') as value:
        def forbidden(*args, **kwargs):
            pytest.fail('Team metadata must not resolve credentials or invoke a Provider')
        value.app.state.service.agent_runtime.credentials.resolve = forbidden
        value.app.state.service.agent_runtime.adapters.require = forbidden
        yield value


def post(client, path, body, key, status=201):
    response = client.post(BASE + path, json=body, headers={'Idempotency-Key': key})
    assert response.status_code == status, response.text
    return response.json()


def agent(client, ident, workspace='ws_local'):
    return post(client, f'/workspaces/{workspace}/agents', {
        'actor_id': 'local_admin', 'workspace_id': workspace, 'id': ident,
        'kind': 'agent', 'display_name': ident, 'clearance': 'Restricted',
    }, 'agent-' + ident)['agent']


def channel(client, ident, classification='Internal', workspace='ws_local'):
    return post(client, f'/workspaces/{workspace}/channels', {
        'actor_id': 'local_admin', 'id': ident, 'title': 'title-' + ident,
        'data_class': classification,
    }, 'channel-' + ident)['channel']


def member(client, channel_id, actor, roles=None):
    return post(client, f'/channels/{channel_id}/memberships', {
        'actor_id': 'local_admin', 'agent_id': actor, 'roles': roles or ['observer'],
    }, 'member-' + channel_id + '-' + actor)


def read(client, path, actor='local_admin', **params):
    return client.get(BASE + path, params={'actor_id': actor, **params})


def error(response, status, code):
    assert response.status_code == status, response.text
    assert response.json()['error']['code'] == code
    assert 'items' not in response.json()


def validate_response(client, path_template, method, status, payload):
    document = client.get('/openapi.json').json()
    schema = document['paths'][BASE + path_template][method]['responses'][str(status)]['content']['application/json']['schema']
    assert schema
    check = Draft202012Validator({**document, **schema}, format_checker=FormatChecker())
    check.validate(payload)
    assert not check.is_valid({**payload, 'unexpected': True})


def change_state(client, table, identity, definition, **changes):
    # Fault injection only in this test's temporary database, not a public revoke API.
    assert table in {'team_workspaces', 'team_agent_identities', 'team_channels',
                     'team_workspace_memberships', 'team_channel_memberships'}
    assert set(identity) <= {'id', 'workspace_id', 'channel_id', 'agent_id'}
    where = ' AND '.join(key + '=?' for key in identity)
    with client.app.state.service.store.transaction() as db:
        original = json.loads(db.execute(f'SELECT doc FROM {table} WHERE {where}', tuple(identity.values())).fetchone()['doc'])
        updated = {**original, **changes}
        validate_contract(definition, updated)
        db.execute(f'UPDATE {table} SET doc=? WHERE {where}', (json.dumps(updated), *identity.values()))
    return original


@pytest.mark.parametrize('transition,status,code', [
    ('revoked', 403, 'TEAM_CHANNEL_ACCESS_DENIED'),
    ('archived', 409, 'TEAM_CHANNEL_ARCHIVED'),
    ('clearance', 403, 'TEAM_DATA_CLEARANCE_DENIED'),
])
def test_channel_list_rechecks_current_detail_visibility(client, transition, status, code):
    actor = agent(client, 'reader-59')['id']
    hidden = channel(client, 'ch_hidden59', 'Restricted')
    visible = channel(client, 'ch_visible59')
    member(client, hidden['id'], actor)
    member(client, visible['id'], actor)
    before = read(client, '/workspaces/ws_local/channels', actor)
    assert before.status_code == 200 and {x['id'] for x in before.json()['items']} == {hidden['id'], visible['id']}
    detail = read(client, '/channels/' + hidden['id'], actor)
    assert detail.status_code == 200 and detail.json()['channel'] == hidden
    validate_response(client, '/channels/{channel_id}', 'get', 200, detail.json())
    if transition == 'revoked':
        change_state(client, 'team_channel_memberships', {'channel_id': hidden['id'], 'agent_id': actor},
                     'channel_membership', status='revoked')
    elif transition == 'archived':
        change_state(client, 'team_channels', {'id': hidden['id']}, 'channel', status='archived')
    else:
        change_state(client, 'team_workspace_memberships', {'workspace_id': 'ws_local', 'agent_id': actor},
                     'workspace_membership', clearance='Internal')
    error(read(client, '/channels/' + hidden['id'], actor), status, code)
    after = read(client, '/workspaces/ws_local/channels', actor)
    assert after.status_code == 200
    assert after.json()['items'] == [visible]
    assert hidden['id'] not in after.text and hidden['title'] not in after.text
    validate_response(client, '/workspaces/{workspace_id}/channels', 'get', 200, after.json())


def test_workspace_create_membership_and_agent_directory_roundtrip(client):
    reader = agent(client, 'reader-59')
    unrelated = agent(client, 'unrelated-59')
    body = {'actor_id': 'local_admin', 'id': 'ws_second59', 'name': 'Second workspace', 'data_class': 'Restricted'}
    denied = post(client, '/workspaces', {**body, 'actor_id': reader['id']}, 'nonadmin', 403)
    assert denied['error']['code'] == 'TEAM_BOOTSTRAP_ADMIN_REQUIRED'
    assert [w['id'] for w in read(client, '/workspaces').json()['items']] == ['ws_local']
    created = post(client, '/workspaces', body, 'workspace')
    validate_response(client, '/workspaces', 'post', 201, created)
    assert post(client, '/workspaces', body, 'workspace') == created
    conflict = post(client, '/workspaces', {**body, 'name': 'Altered'}, 'workspace', 409)
    assert conflict['error']['code'] == 'CONFLICT'
    path = '/workspaces/' + created['id']
    assert read(client, path).json()['workspace'] == created
    for suffix in ('', '/agents', '/channels'):
        error(read(client, path + suffix, reader['id']), 403, 'TEAM_WORKSPACE_ACCESS_DENIED')
    members = {'actor_id': 'local_admin', 'agent_id': reader['id'], 'role': 'member', 'clearance': 'Internal'}
    granted = post(client, path + '/memberships', members, 'grant')
    validate_contract('workspace_membership', granted)
    assert post(client, path + '/memberships', members, 'grant') == granted
    assert len(read(client, path).json()['memberships']) == 2
    duplicate = post(client, path + '/memberships', members, 'other-grant', 409)
    assert duplicate['error']['code'] == 'CONFLICT'
    conflicting = post(client, path + '/memberships', {**members, 'role': 'admin'}, 'grant', 409)
    assert conflicting['error']['code'] == 'CONFLICT'
    for actor in ('local_admin', reader['id']):
        listing = read(client, path + '/agents', actor)
        assert listing.status_code == 200
        assert {a['id'] for a in listing.json()['items']} == {'local_admin', reader['id']}
        assert unrelated['id'] not in listing.text
        validate_response(client, '/workspaces/{workspace_id}/agents', 'get', 200, listing.json())
    rejected = post(client, path + '/memberships', {**members, 'actor_id': reader['id'], 'agent_id': unrelated['id']}, 'member-grant', 403)
    assert rejected['error']['code'] == 'TEAM_WORKSPACE_ADMIN_REQUIRED'
    missing = post(client, path + '/memberships', {**members, 'agent_id': 'absent-59'}, 'missing-grant', 404)
    assert missing['error']['code'] == 'TEAM_AGENT_NOT_FOUND'
    assert len(read(client, path).json()['memberships']) == 2
    assert read(client, path + '/channels', reader['id']).json()['items'] == []


@pytest.mark.parametrize('path,body', [
    ('/workspaces', {'actor_id': 'local_admin', 'id': 'ws_invalid59', 'name': 'Invalid', 'data_class': 'Unknown'}),
    ('/workspaces/ws_local/memberships', {'actor_id': 'local_admin', 'agent_id': 'reader-59', 'role': 'superuser', 'clearance': 'Internal'}),
])
def test_foundation_invalid_write_does_not_change_state(client, path, body):
    before = read(client, '/workspaces/ws_local').json()
    invalid = post(client, path, body, 'invalid', 422)
    assert invalid['error']['code'] == 'TEAM_FOUNDATION_CONTRACT_INVALID'
    assert read(client, '/workspaces/ws_local').json() == before
    assert [w['id'] for w in read(client, '/workspaces').json()['items']] == ['ws_local']


@pytest.mark.parametrize('path,body', [
    ('/workspaces', {'actor_id': 'local_admin', 'id': 'ws_missingkey59', 'name': 'No key', 'data_class': 'Internal'}),
    ('/workspaces/ws_local/memberships', {'actor_id': 'local_admin', 'agent_id': 'reader-59', 'role': 'member', 'clearance': 'Internal'}),
])
def test_foundation_write_requires_key_before_state_change(client, path, body):
    response = client.post(BASE + path, json=body)
    error(response, 422, 'VALIDATION_ERROR')
    assert [w['id'] for w in read(client, '/workspaces').json()['items']] == ['ws_local']
    assert len(read(client, '/workspaces/ws_local').json()['memberships']) == 1


@pytest.mark.parametrize('path', ['/workspaces/ws_local/agents', '/workspaces/ws_local/channels', '/sessions'])
def test_team_lists_validate_actor_and_required_parameter(client, path):
    error(client.get(BASE + path), 422, 'VALIDATION_ERROR')
    error(read(client, path, 'absent-59'), 404, 'TEAM_AGENT_NOT_FOUND')
    actor = agent(client, 'suspended-59')['id']
    change_state(client, 'team_agent_identities', {'id': actor}, 'agent_identity', status='suspended')
    error(read(client, path, actor), 403, 'TEAM_AGENT_SUSPENDED')


@pytest.mark.parametrize('transition,status,code', [
    ('revoked', 403, 'TEAM_WORKSPACE_ACCESS_DENIED'),
    ('archived', 409, 'TEAM_WORKSPACE_ARCHIVED'),
])
def test_workspace_invalidity_denies_lists_without_leaking_rows(client, transition, status, code):
    actor = agent(client, 'reader-59')['id']
    hidden = channel(client, 'ch_hidden59')
    member(client, hidden['id'], actor)
    if transition == 'revoked':
        change_state(client, 'team_workspace_memberships', {'workspace_id': 'ws_local', 'agent_id': actor},
                     'workspace_membership', status='revoked')
    else:
        change_state(client, 'team_workspaces', {'id': 'ws_local'}, 'workspace', status='archived')
    for path in ('/workspaces/ws_local/agents', '/workspaces/ws_local/channels', '/channels/' + hidden['id']):
        response = read(client, path, actor)
        error(response, status, code)
        assert hidden['title'] not in response.text


def test_missing_workspace_and_channel_return_explicit_not_found(client):
    error(read(client, '/workspaces/ws_absent59/agents'), 404, 'TEAM_WORKSPACE_NOT_FOUND')
    error(read(client, '/workspaces/ws_absent59/channels'), 404, 'TEAM_WORKSPACE_NOT_FOUND')
    error(read(client, '/channels/ch_absent59'), 404, 'TEAM_CHANNEL_NOT_FOUND')
    error(read(client, '/sessions', channel_id='ch_absent59'), 404, 'TEAM_CHANNEL_NOT_FOUND')


def test_channel_list_does_not_turn_unexpected_failures_into_empty_success(client, monkeypatch):
    channel(client, 'ch_visible59')
    from backend.analysis import Problem
    def broken(*args, **kwargs):
        raise Problem('FIXTURE_STORAGE_FAILURE', 'Storage failure', 503)
    monkeypatch.setattr(client.app.state.service.team_foundation, 'assert_channel_access', broken)
    error(read(client, '/workspaces/ws_local/channels'), 503, 'FIXTURE_STORAGE_FAILURE')


def session(client, actor, channel_id, key):
    return post(client, '/sessions', {'actor_id': actor, 'workspace_id': 'ws_local', 'channel_id': channel_id}, key)


def test_session_list_is_owner_scoped_filters_channels_and_retains_history(client):
    actor = agent(client, 'reader-59')['id']
    other = agent(client, 'other-59')['id']
    first = channel(client, 'ch_first59')
    second = channel(client, 'ch_second59')
    member(client, first['id'], actor)
    member(client, second['id'], actor)
    member(client, first['id'], other)
    empty = read(client, '/sessions', actor)
    assert empty.status_code == 200 and empty.json()['items'] == []
    validate_response(client, '/sessions', 'get', 200, empty.json())
    own_first = session(client, actor, first['id'], 'first')['session']
    own_second = session(client, actor, second['id'], 'second')['session']
    foreign = session(client, other, first['id'], 'foreign')['session']
    all_own = read(client, '/sessions', actor)
    assert all_own.status_code == 200 and all_own.json()['items'] == [own_second, own_first]
    assert foreign['id'] not in all_own.text
    validate_response(client, '/sessions', 'get', 200, all_own.json())
    filtered = read(client, '/sessions', actor, channel_id=first['id'])
    assert filtered.status_code == 200 and filtered.json()['items'] == [own_first]
    retired = post(client, '/sessions/' + own_first['id'] + ':handoff', {
        'actor_id': actor, 'expected_session_version': own_first['version'], 'reason': 'manual_handoff',
    }, 'retire')['session']
    assert retired['status'] == 'retired'
    assert read(client, '/sessions', actor, channel_id=first['id']).json()['items'] == [retired]
    assert read(client, '/sessions', other).json()['items'] == [foreign]
    change_state(client, 'team_channel_memberships', {'channel_id': first['id'], 'agent_id': actor},
                 'channel_membership', status='revoked')
    assert read(client, '/sessions', actor).json()['items'] == [own_second]
    error(read(client, '/sessions', actor, channel_id=first['id']), 403, 'TEAM_CHANNEL_ACCESS_DENIED')
    error(read(client, '/sessions/' + own_first['id'], actor), 403, 'TEAM_CHANNEL_ACCESS_DENIED')
    assert read(client, '/sessions', other).json()['items'] == [foreign]


def test_team_runtime_does_not_claim_authentication_or_execution(client):
    response = client.get(BASE + '/runtime')
    assert response.status_code == 200
    runtime = response.json()
    assert runtime['agent_runtime'] == 'not_connected'
    assert runtime['external_model_calls'] == runtime['external_tool_calls'] == 0
    foundation = client.get(BASE + '/foundation/runtime').json()
    assert foundation['protocol_identity_authentication'] == 'not_connected'
    assert client.app.state.service.store.listing('runs') == []


def test_revoked_channel_stays_hidden_after_database_restart(tmp_path):
    database = tmp_path / 'restart.db'
    with TestClient(create_app(database, False), base_url='http://127.0.0.1') as initial:
        actor = agent(initial, 'reader-59')['id']
        hidden = channel(initial, 'ch_hidden59')
        member(initial, hidden['id'], actor)
        session(initial, actor, hidden['id'], 'session-before-revoke')
        change_state(initial, 'team_channel_memberships', {'channel_id': hidden['id'], 'agent_id': actor},
                     'channel_membership', status='revoked')
    with TestClient(create_app(database, False), base_url='http://127.0.0.1') as restarted:
        channels = read(restarted, '/workspaces/ws_local/channels', actor)
        sessions = read(restarted, '/sessions', actor)
        assert channels.status_code == sessions.status_code == 200
        assert channels.json()['items'] == sessions.json()['items'] == []
        error(read(restarted, '/channels/' + hidden['id'], actor), 403, 'TEAM_CHANNEL_ACCESS_DENIED')
        # An authorized different identity still sees the Channel, not a global deletion.
        assert read(restarted, '/workspaces/ws_local/channels').json()['items'] == [hidden]
