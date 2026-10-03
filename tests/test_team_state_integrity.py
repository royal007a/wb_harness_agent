"""HA-0063: corrupt Foundation rows must be faults, not invisible records."""
import json
from datetime import timedelta

import pytest

from backend.analysis import Problem
from backend.team_coordination import iso_now
from test_team_list_failures import (ACTOR, ROUTES, client, post, seed, update_doc, snapshot_tables)


BASE = '/api/local/team'
KINDS = ['identity', 'workspace', 'workspace_membership', 'channel', 'channel_membership']


def target(created, kind):
    return {
        'identity': ('team_agent_identities', 'id=?', (ACTOR,)),
        'workspace': ('team_workspaces', 'id=?', ('ws_local',)),
        'workspace_membership': ('team_workspace_memberships', 'workspace_id=? AND agent_id=?', ('ws_local', ACTOR)),
        'channel': ('team_channels', 'id=?', (created['channel'],)),
        'channel_membership': ('team_channel_memberships', 'channel_id=? AND agent_id=?', (created['channel'], ACTOR)),
    }[kind]


def damaged(client, created, record_kind, **change):
    update_doc(client, *target(created, record_kind), lambda doc: doc.update(change))


def assert_corrupt(response):
    assert response.status_code == 500, response.text
    body = response.json()
    assert set(body) == {'error'} and body['error']['code'] == 'TEAM_STATE_CORRUPT'
    assert body['error']['message'] == 'Team 持久记录损坏，需人工核对。'
    assert 'items' not in body and 'membership' not in body
    assert ACTOR not in response.text and 'ch_lists60_' not in response.text


def dependent_routes(created, kind):
    routes = [*ROUTES.values(), BASE + '/workspaces/ws_local/channels', BASE + '/channels/' + created['channel']]
    if kind in {'identity', 'workspace', 'workspace_membership'}:
        routes += [BASE + '/workspaces', BASE + '/workspaces/ws_local', BASE + '/workspaces/ws_local/agents']
    return routes


@pytest.mark.parametrize('kind', KINDS)
@pytest.mark.parametrize('status', [None, 'ACTIVE', 'actve'])
def test_unknown_status_is_corruption_not_revocation(client, kind, status):
    created = seed(client)
    damaged(client, created, kind, status=status)
    for route in dependent_routes(created, kind):
        assert_corrupt(client.get(route, params={'actor_id': ACTOR}))


@pytest.mark.parametrize('changed', ['document', 'column'])
def test_channel_sql_scope_mismatch_cannot_move_channel_between_workspaces(client, changed):
    created = seed(client)
    post(client, 'team/workspaces', {'actor_id': 'local_admin', 'id': 'ws_other63',
         'name': 'Other workspace', 'data_class': 'Restricted'}, 'workspace-other')
    post(client, 'team/workspaces/ws_other63/memberships', {'actor_id': 'local_admin',
         'agent_id': ACTOR, 'role': 'member', 'clearance': 'Restricted'}, 'member-other')
    # Actor legitimately belongs to both: denial cannot be disguised as missing membership.
    if changed == 'document':
        damaged(client, created, 'channel', workspace_id='ws_other63')
    else:
        with client.app.state.service.store.transaction() as db:
            db.execute('UPDATE team_channels SET workspace_id=? WHERE id=?', ('ws_other63', created['channel']))
    scope = 'ws_local' if changed == 'document' else 'ws_other63'
    assert_corrupt(client.get(BASE + '/workspaces/' + scope + '/channels', params={'actor_id': ACTOR}))
    for route in [*ROUTES.values(), BASE + '/channels/' + created['channel']]:
        assert_corrupt(client.get(route, params={'actor_id': ACTOR}))


def test_channel_filters_code_and_status_together(client, monkeypatch):
    seed(client)
    def failed(*args, **kwargs):
        raise Problem('TEAM_CHANNEL_ACCESS_DENIED', 'Synthetic backend failure.', 503)
    monkeypatch.setattr(client.app.state.service.team_foundation, 'assert_channel_access', failed)
    response = client.get(BASE + '/workspaces/ws_local/channels', params={'actor_id': ACTOR})
    assert response.status_code == 503 and response.json()['error']['code'] == 'TEAM_CHANNEL_ACCESS_DENIED'
    assert 'items' not in response.json()


@pytest.mark.parametrize('kind,changes', [
    ('identity', {'id': 'local_admin'}), ('workspace', {'id': 'ws_other63'}),
    ('workspace_membership', {'agent_id': 'local_admin'}),
    ('workspace_membership', {'workspace_id': 'ws_other63'}),
    ('channel', {'id': 'ch_different63'}),
    ('channel_membership', {'agent_id': 'local_admin'}),
    ('channel_membership', {'channel_id': 'ch_different63'}),
    ('identity', {'kind': 'unknown'}), ('workspace', {'data_class': 'Secret'}),
    ('workspace_membership', {'role': 'superuser'}), ('channel_membership', {'roles': []}),
    ('channel', {'version': True}),
])
def test_record_shape_and_sql_key_binding_before_access(client, kind, changes):
    created = seed(client)
    damaged(client, created, kind, **changes)
    for route in dependent_routes(created, kind):
        assert_corrupt(client.get(route, params={'actor_id': ACTOR}))


@pytest.mark.parametrize('kind', KINDS)
@pytest.mark.parametrize('raw', ['{not-json', 'null', '[]'])
def test_invalid_json_or_nonobject_record_is_server_fault(client, kind, raw):
    created = seed(client)
    table, where, args = target(created, kind)
    with client.app.state.service.store.transaction() as db:
        db.execute(f'UPDATE {table} SET doc=? WHERE {where}', (raw, *args))
    for route in dependent_routes(created, kind):
        assert_corrupt(client.get(route, params={'actor_id': ACTOR}))


@pytest.mark.parametrize('kind,route,changes', [
    ('identity', '/workspaces/ws_local/agents', {'status': 'actve'}),
    ('workspace_membership', '/workspaces/ws_local/agents', {'agent_id': 'local_admin'}),
    ('workspace_membership', '/workspaces/ws_local', {'role': 'superuser'}),
    ('channel_membership', '/channels/CHANNEL', {'agent_id': 'local_admin'}),
])
def test_directory_and_membership_arrays_validate_noncaller_records(client, kind, route, changes):
    created = seed(client)
    damaged(client, created, kind, **changes)
    # Admin remains valid: the corrupt row is in the returned array, not the caller check.
    assert_corrupt(client.get(BASE + route.replace('CHANNEL', created['channel']), params={'actor_id': 'local_admin'}))


def test_legal_inactive_directory_and_memberships_remain_inspectable(client):
    created = seed(client)
    damaged(client, created, 'identity', status='suspended')
    damaged(client, created, 'workspace_membership', status='revoked')
    damaged(client, created, 'channel_membership', status='revoked')
    directory = client.get(BASE + '/workspaces/ws_local/agents', params={'actor_id': 'local_admin'})
    assert directory.status_code == 200
    assert next(a for a in directory.json()['items'] if a['id'] == ACTOR)['status'] == 'suspended'
    for route in ['/workspaces/ws_local', '/channels/' + created['channel']]:
        response = client.get(BASE + route, params={'actor_id': 'local_admin'})
        assert response.status_code == 200
        assert next(m for m in response.json()['memberships'] if m['agent_id'] == ACTOR)['status'] == 'revoked'
    rejected = client.get(BASE + '/workspaces', params={'actor_id': ACTOR})
    assert rejected.status_code == 403 and rejected.json()['error']['code'] == 'TEAM_AGENT_SUSPENDED'


def test_corrupt_authorizer_does_not_write_task_or_idempotency(client):
    created = seed(client)
    damaged(client, created, 'workspace', status='actve')
    tables = ['team_sessions', 'team_session_handoffs', 'idempotency']
    before = snapshot_tables(client, tables)
    response = client.post(BASE + '/sessions', json={'actor_id': ACTOR, 'workspace_id': 'ws_local',
        'channel_id': created['channel']}, headers={'Idempotency-Key': 'must-not-write'})
    assert_corrupt(response)
    assert snapshot_tables(client, tables) == before


def test_recovery_corruption_rolls_back_expiry_without_partial_result(client):
    good, bad = seed(client, 'good'), seed(client, 'bad')
    expired = (iso_now() - timedelta(seconds=1)).isoformat().replace('+00:00', 'Z')
    for item in [good, bad]:
        update_doc(client, 'recovery_cases', 'id=?', (item['recovery']['id'],), lambda doc: doc.update(deadline_at=expired))
    damaged(client, bad, 'channel_membership', status='ACTIVE')
    tables = ['recovery_cases', 'team_tasks', 'team_attention_items', 'team_attention_leases', 'team_sessions', 'idempotency']
    before = snapshot_tables(client, tables)
    assert_corrupt(client.get(ROUTES['recovery'], params={'actor_id': ACTOR}))
    assert snapshot_tables(client, tables) == before


@pytest.mark.parametrize('kind', KINDS)
@pytest.mark.parametrize('change', ['missing_status', 'unexpected_field'])
def test_required_and_additional_fields_are_checked_on_storage_reads(client, kind, change):
    created = seed(client)
    def mutate(doc):
        if change == 'missing_status':
            doc.pop('status')
        else:
            doc['unexpected'] = 'must not escape'
    update_doc(client, *target(created, kind), mutate)
    for route in dependent_routes(created, kind):
        assert_corrupt(client.get(route, params={'actor_id': ACTOR}))


def test_inbox_corruption_rolls_back_expired_lease(client):
    created = seed(client)
    post(client, 'team/attention/items/' + created['inbox']['id'] + ':claim', {
        'actor_id': ACTOR, 'lease_seconds': 300,
    }, 'attention-claim', 200)
    expired = (iso_now() - timedelta(seconds=1)).isoformat().replace('+00:00', 'Z')
    update_doc(client, 'team_attention_items', 'id=?', (created['inbox']['id'],),
               lambda doc: doc['lease'].update(expires_at=expired))
    damaged(client, created, 'channel_membership', status='actve')
    tables = ['team_attention_items', 'team_attention_leases', 'team_attention_work_marks']
    before = snapshot_tables(client, tables)
    assert_corrupt(client.get(ROUTES['inbox'], params={'actor_id': ACTOR}))
    assert snapshot_tables(client, tables) == before


def test_corrupt_actor_is_rejected_before_empty_list_scan(client):
    update_doc(client, 'team_agent_identities', 'id=?', (ACTOR,), lambda doc: doc.update(status='ACTIVE'))
    for route in [*ROUTES.values(), BASE + '/workspaces/ws_local/channels', BASE + '/workspaces']:
        assert_corrupt(client.get(route, params={'actor_id': ACTOR}))
