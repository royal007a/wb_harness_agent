"""HA-0070: synthetic logical deletion, not disk/WAL erasure or live data."""
import copy
import json
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

import pytest
from fastapi.testclient import TestClient
from jsonschema import Draft202012Validator

from backend.app import create_app
from backend.memory import MemoryPlane, CONTRACT
from backend.store import dumps
from test_read_surfaces import client, post_bank
from test_memory_write_contracts import body, check, OPERATIONS
from test_product_contract_boundaries import snapshot


MARKER = {'schema_version': 'memory-receipt-tombstone@1', 'receipt_status': 'unavailable'}


def post(c, path, request, key):
    response = c.post(path, json=request, headers={'Idempotency-Key': key})
    assert response.status_code == 201, response.text
    return response.json()


def rows(c):
    return {(r['scope'], r['key']): dict(r) for r in
            c.app.state.service.store.db.execute('SELECT * FROM idempotency')}


def world(c):
    bank = post_bank(c, 'receipts70', 'bank70')
    base = '/api/local/memory/banks/' + bank['id']
    calls, receipts = {}, {}

    def create(label, operation, request):
        path = base + '/' + operation
        for suffix in ['', '-dedup']:
            key = label + suffix
            receipts[key] = post(c, path, request, key)
            calls[key] = (path, request, key)
        return receipts[label]

    a = create('a', 'retain', body('ERASE_SENTINEL70'))
    b = create('b', 'retain', body('KEEP_SENTINEL70'))

    def entity(label, source):
        return create(label, 'entities', {'canonical_name': label + '_NAME_SENTINEL70',
            'entity_type': 'system', 'aliases': [label + '_ALIAS_SENTINEL70'],
            'support_fact_id': source['facts'][0]['id'], 'valid_from': None, 'valid_to': None})

    ea, eb, ec = entity('ea', a), entity('eb', b), entity('ec', b)

    def relation(label, subject, object_, source, predicate):
        return create(label, 'relations', {'subject_entity_id': subject['entity']['id'],
            'object_entity_id': object_['entity']['id'], 'predicate': predicate,
            'support_fact_id': source['facts'][0]['id'], 'confidence': 1,
            'occurred_at': '2026-01-01T00:00:00Z', 'valid_from': None, 'valid_to': None})

    relation('indirect', ea, eb, b, 'depends_on')
    relation('direct', eb, ec, a, 'affects')
    relation('keep', eb, ec, b, 'depends_on')
    other = post_bank(c, 'other70', 'bank-other70')
    # Independent Bank may explicitly store the same content; deletion is scoped.
    post(c, '/api/local/memory/banks/' + other['id'] + '/retain', body('ERASE_SENTINEL70'), 'a')
    return {'bank': bank, 'source': a['source']['id'], 'calls': calls, 'receipts': receipts,
            'affected': [name + suffix for name in ['a', 'ea', 'indirect', 'direct']
                         for suffix in ['', '-dedup']], 'base': base}


def delete(c, w):
    return c.delete('/api/local/memory/sources/' + w['source'], headers={'Idempotency-Key': 'delete70'})


def replay(c, w, key):
    path, request, ident = w['calls'][key]
    return c.post(path, json=request, headers={'Idempotency-Key': ident})


def unavailable(response):
    assert response.status_code == 409, response.text
    assert response.json()['error']['code'] == 'MEMORY_RECEIPT_UNAVAILABLE', response.text
    assert 'SENTINEL70' not in response.text


@pytest.mark.parametrize('key', ['a', 'a-dedup', 'ea', 'ea-dedup', 'direct', 'direct-dedup', 'indirect', 'indirect-dedup'])
def test_deleted_content_receipt_cannot_replay_or_write(client, key):
    w = world(client)
    assert delete(client, w).status_code == 200
    before = snapshot(client)
    response = replay(client, w, key)
    unavailable(response)
    if key.startswith('a'):
        check(client, OPERATIONS[0], response.json(), '409')
    assert snapshot(client) == before


def test_all_and_only_related_payloads_removed_with_digest_preserved(client):
    w = world(client)
    before = rows(client)
    response = delete(client, w)
    assert response.status_code == 200
    assert response.json()['deleted_entity_count'] == 1
    assert response.json()['deleted_relation_count'] == 2
    audit = client.app.state.service.store.db.execute('SELECT doc FROM memory_audit WHERE id=?',
                                                      (response.json()['audit_id'],)).fetchone()
    assert json.loads(audit['doc'])['metadata'].get('invalidated_receipt_count') == 8
    after = rows(client)
    marker_validator = Draft202012Validator({'$defs': CONTRACT['$defs'], '$ref': '#/$defs/receipt_tombstone'})
    for pair, old in before.items():
        new = after[pair]
        affected = pair[0].endswith(w['bank']['id']) and pair[1] in w['affected']
        if affected:
            assert new['digest'] == old['digest']
            assert json.loads(new['response']) == MARKER
            marker_validator.validate(json.loads(new['response']))
        else:
            assert new == old
    for key in ['b', 'b-dedup', 'eb', 'ec', 'keep', 'keep-dedup']:
        assert replay(client, w, key).json() == w['receipts'][key]
    current = snapshot(client)
    assert delete(client, w).json() == response.json()
    assert snapshot(client) == current


@pytest.mark.parametrize('key', ['a', 'ea', 'indirect'])
def test_invalidated_key_still_detects_conflict_before_unavailable(client, key):
    w = world(client)
    assert delete(client, w).status_code == 200
    path, request, ident = w['calls'][key]
    changed = copy.deepcopy(request)
    if key == 'a':
        changed['facts'][0]['statement'] += ' changed'
    elif key == 'ea':
        changed['canonical_name'] += ' changed'
    else:
        changed['confidence'] = 0.5
    before = snapshot(client)
    response = client.post(path, json=changed, headers={'Idempotency-Key': ident})
    assert response.status_code == 409 and response.json()['error']['code'] == 'CONFLICT'
    assert snapshot(client) == before


def test_explicit_new_key_does_not_resurrect_old_receipt(client):
    w = world(client)
    assert delete(client, w).status_code == 200
    path, request, _ = w['calls']['a']
    new = post(client, path, request, 'explicit-new70')
    assert new['source']['id'] != w['source'] and new['deduplicated'] is False
    before = snapshot(client)
    unavailable(replay(client, w, 'a'))
    assert snapshot(client) == before


def test_retract_and_supersede_are_not_deletion(client):
    w = world(client)
    source_path = '/api/local/memory/sources/' + w['source']
    replacement = body('replacement70')
    replacement['facts'][0]['supersedes_fact_id'] = w['receipts']['a']['facts'][0]['id']
    post(client, w['base'] + '/retain', replacement, 'supersede70')
    response = client.post(source_path + ':retract', json={}, headers={'Idempotency-Key': 'retract70'})
    assert response.status_code == 200
    for key in w['affected']:
        assert replay(client, w, key).json() == w['receipts'][key]
    assert delete(client, w).status_code == 200
    before = snapshot(client)
    assert client.post(source_path + ':retract', json={}, headers={'Idempotency-Key': 'retract70'}).json() == response.json()
    assert snapshot(client) == before


@pytest.mark.parametrize('stage', ['redaction', 'audit', 'receipt'])
def test_failure_rolls_back_canonical_and_receipt_payloads(client, stage):
    w = world(client)
    store = client.app.state.service.store
    trigger = {
        'redaction': "BEFORE UPDATE OF response ON idempotency WHEN OLD.scope LIKE 'memory:relations:%'",
        'audit': "BEFORE INSERT ON memory_audit WHEN json_extract(NEW.doc, '$.event_type')='memory.source.deleted'",
        'receipt': "BEFORE INSERT ON idempotency WHEN NEW.scope LIKE 'memory:delete:%'",
    }[stage]
    store.db.execute("CREATE TEMP TRIGGER fail70 " + trigger + " BEGIN SELECT RAISE(ABORT, 'injected'); END")
    before = snapshot(client)[1]
    client._transport.raise_server_exceptions = False
    response = delete(client, w)
    assert response.status_code == 500
    assert 'SENTINEL70' not in response.text
    assert snapshot(client)[1] == before
    store.db.execute('DROP TRIGGER fail70')
    for key in w['affected']:
        assert replay(client, w, key).json() == w['receipts'][key]
    assert delete(client, w).status_code == 200
    unavailable(replay(client, w, 'a'))


def legacy_orphans(c):
    w = world(c)
    originals = rows(c)
    assert delete(c, w).status_code == 200
    store = c.app.state.service.store
    # Recreate exactly the pre-fix representation in a temporary DB.
    with store.transaction() as db:
        for pair, record in originals.items():
            db.execute('UPDATE idempotency SET response=? WHERE scope=? AND key=?',
                       (record['response'], *pair))
    return w


def test_old_orphan_replay_is_rejected_without_lazy_write(client):
    w = legacy_orphans(client)
    before = snapshot(client)
    for key in w['affected']:
        unavailable(replay(client, w, key))
    assert snapshot(client) == before


def test_new_app_cleans_legacy_orphans_and_repeated_cleanup_is_noop(client):
    w = legacy_orphans(client)
    store = client.app.state.service.store
    database = store.db.execute('PRAGMA database_list').fetchone()['file']
    client.__exit__(None, None, None)
    with TestClient(create_app(database, False), base_url='http://127.0.0.1') as restarted:
        for pair, record in rows(restarted).items():
            if pair[0].endswith(w['bank']['id']) and pair[1] in w['affected']:
                assert json.loads(record['response']) == MARKER
        before = snapshot(restarted)
        for key in w['affected']:
            unavailable(replay(restarted, w, key))
        # Only receipt cleanup is a no-op; startup FTS rebuild writes separately.
        plane = restarted.app.state.service.memory
        with plane.store.transaction() as db:
            assert plane._redact_orphaned_receipts(db) == 0
        assert snapshot(restarted) == before
        assert replay(restarted, w, 'b').json() == w['receipts']['b']


@pytest.mark.parametrize('bad', ['json', 'binding', 'db'])
def test_startup_cleanup_does_not_hide_fault_or_partially_scrub(client, bad):
    w = legacy_orphans(client)
    store = client.app.state.service.store
    if bad != 'db':
        mismatched = copy.deepcopy(w['receipts']['b'])
        mismatched['source']['bank_id'] = 'membank_' + '0' * 32
        payload = '{invalid JSON' if bad == 'json' else dumps(mismatched)
        store.db.execute('UPDATE idempotency SET response=? WHERE scope=? AND key=?',
                         (payload, 'memory:retain:' + w['bank']['id'], 'b'))
    else:
        store.db.execute("CREATE TEMP TRIGGER fail_cleanup70 BEFORE UPDATE OF response ON idempotency "
                         "WHEN OLD.scope LIKE 'memory:relations:%' BEGIN SELECT RAISE(ABORT, 'injected'); END")
    before = snapshot(client)[1]
    with pytest.raises(Exception) as exc:
        MemoryPlane(store)
    if bad == 'db':
        assert isinstance(exc.value, sqlite3.DatabaseError)
    else:
        assert getattr(exc.value, 'code', '') == 'MEMORY_RECEIPT_CORRUPT'
    assert snapshot(client)[1] == before


def test_unknown_scope_and_user_text_are_not_dependency_keys(client):
    w = world(client)
    store = client.app.state.service.store
    other = ('product:fixture70', 'unrelated', 'digest', '{unparsed:' + w['source'])
    store.db.execute('INSERT INTO idempotency VALUES(?,?,?,?)', other)
    request = body('copy70')
    request['facts'][0]['statement'] = w['source'] + ' ea_NAME_SENTINEL70'
    kept = post(client, w['base'] + '/retain', request, 'text-is-not-dependency70')
    assert delete(client, w).status_code == 200
    assert tuple(store.db.execute('SELECT * FROM idempotency WHERE scope=?', (other[0],)).fetchone()) == other
    assert post(client, w['base'] + '/retain', request, 'text-is-not-dependency70') == kept


def test_delete_does_not_run_startup_cleanup_for_another_bank(client):
    w = world(client)
    extra = post_bank(client, 'legacy-other70', 'legacy-bank70')
    path = '/api/local/memory/banks/' + extra['id'] + '/retain'
    retained = post(client, path, body('other-orphan70'), 'legacy70')
    pair = ('memory:retain:' + extra['id'], 'legacy70')
    original = rows(client)[pair]
    assert client.delete('/api/local/memory/sources/' + retained['source']['id'],
                         headers={'Idempotency-Key': 'legacy-delete70'}).status_code == 200
    store = client.app.state.service.store
    store.db.execute('UPDATE idempotency SET response=? WHERE scope=? AND key=?', (original['response'], *pair))
    assert delete(client, w).status_code == 200
    assert rows(client)[pair] == original
    before = snapshot(client)
    unavailable(client.post(path, json=body('other-orphan70'), headers={'Idempotency-Key': 'legacy70'}))
    assert snapshot(client) == before


@pytest.mark.parametrize('bad', [{}, {**MARKER, 'response': 'PRIVATE'}, {**MARKER, 'receipt_status': 'active'},
                               {**MARKER, 'schema_version': 'memory-receipt-tombstone@2'}])
def test_marker_contract_is_strict(bad):
    validator = Draft202012Validator({'$defs': CONTRACT['$defs'], '$ref': '#/$defs/receipt_tombstone'})
    validator.validate(MARKER)
    assert not validator.is_valid(bad)


def test_delete_and_replay_serialize_without_resurrection(client):
    w = world(client)
    plane = client.app.state.service.memory
    request = w['calls']['a'][1]
    barrier = Barrier(2)
    outcomes = []
    def run(which):
        barrier.wait(timeout=5)
        if which == 'delete':
            return plane.delete_source(w['source'], 'delete70')
        try:
            return plane.retain(w['bank']['id'], request, 'a')
        except Exception as exc:
            assert getattr(exc, 'code', '') == 'MEMORY_RECEIPT_UNAVAILABLE'
            return 'unavailable'
    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(pool.map(run, ['delete', 'replay']))
    assert outcomes[0]['status'] == 'deleted'
    assert outcomes[1] in ['unavailable', w['receipts']['a']]
    before = snapshot(client)
    unavailable(replay(client, w, 'a'))
    assert snapshot(client) == before
    assert client.app.state.service.store.db.execute('SELECT count(*) FROM memory_sources WHERE id=?', (w['source'],)).fetchone()[0] == 0


@pytest.mark.parametrize('operation', ['replay', 'delete'])
def test_receipt_authorization_and_purge_share_one_immediate_transaction(client, operation):
    w = world(client)
    store = client.app.state.service.store
    statements = []
    store.db.set_trace_callback(statements.append)
    try:
        response = replay(client, w, 'a') if operation == 'replay' else delete(client, w)
    finally:
        store.db.set_trace_callback(None)
    assert response.status_code == (201 if operation == 'replay' else 200)
    boundaries = [sql for sql in statements if sql in ['BEGIN', 'BEGIN IMMEDIATE', 'COMMIT', 'ROLLBACK']]
    assert boundaries == ['BEGIN IMMEDIATE', 'COMMIT']
    assert statements[0] == 'BEGIN IMMEDIATE' and statements[-1] == 'COMMIT'
    receipt_reads = [i for i, sql in enumerate(statements) if sql.startswith('SELECT digest,response FROM idempotency')]
    source_reads = [i for i, sql in enumerate(statements) if sql.startswith('SELECT 1 FROM memory_sources')]
    assert len(receipt_reads) == 1 and source_reads and receipt_reads[0] < source_reads[0]
    if operation == 'delete':
        assert sum(sql.startswith('UPDATE idempotency SET response=') for sql in statements) == 8


def test_replay_database_fault_is_not_unavailable_or_success(client):
    w = world(client)
    store = client.app.state.service.store
    before = snapshot(client)
    client._transport.raise_server_exceptions = False
    store.db.set_authorizer(lambda action, first, *rest: sqlite3.SQLITE_DENY
                            if action == sqlite3.SQLITE_READ and first == 'memory_sources' else sqlite3.SQLITE_OK)
    try:
        response = replay(client, w, 'a')
    finally:
        store.db.set_authorizer(None)
    assert response.status_code == 500 and response.json()['error']['code'] == 'INTERNAL_ERROR'
    assert 'SENTINEL70' not in response.text
    assert snapshot(client) == before
