"""HA-0071: temporary SQLite with narrowly injected SQL faults, no live service."""
import sqlite3

import pytest
from fastapi.testclient import TestClient

from backend.app import create_app
from backend.memory import MemoryPlane
from backend.store import Store
from test_memory_write_contracts import body, check, OPERATIONS
from test_memory_research_read_contracts import validate, OPERATIONS as READS
from test_product_contract_boundaries import snapshot
from test_read_surfaces import post_bank


def sql_error(message='no such module: fts5', code=sqlite3.SQLITE_ERROR):
    error = sqlite3.OperationalError(message)
    error.sqlite_errorcode = code
    return error


@pytest.fixture
def fault(monkeypatch):
    """A real SQLite connection except at the explicitly selected SQL boundary."""
    control = {'prefix': None, 'error': None, 'calls': [], 'before_commit': None}
    original = sqlite3.connect

    class Connection(sqlite3.Connection):
        def observe(self, statement):
            control['calls'].append(statement)
            if statement == 'COMMIT' and control['before_commit']:
                control['before_commit']()
            if control['prefix'] and statement.startswith(control['prefix']):
                raise control['error']

        def execute(self, statement, *args, **kwargs):
            self.observe(statement)
            return super().execute(statement, *args, **kwargs)

        def executemany(self, statement, *args, **kwargs):
            self.observe(statement)
            return super().executemany(statement, *args, **kwargs)

    monkeypatch.setattr(sqlite3, 'connect', lambda *a, **kw: original(*a, **kw, factory=Connection))
    return control


def fail(fault, prefix, error=None):
    fault.update(prefix=prefix, error=error if error is not None else sql_error())


@pytest.fixture
def client(tmp_path, fault):
    with TestClient(create_app(tmp_path / 'fts.db', False), base_url='http://127.0.0.1',
                    raise_server_exceptions=False) as c:
        def forbidden(*args, **kwargs):
            pytest.fail('Memory tests must not resolve credentials or invoke Providers')
        c.app.state.service.agent_runtime.credentials.resolve = forbidden
        c.app.state.service.agent_runtime.adapters.require = forbidden
        yield c


@pytest.fixture
def unavailable(tmp_path, fault):
    fail(fault, 'CREATE VIRTUAL TABLE')
    with TestClient(create_app(tmp_path / 'missing.db', False), base_url='http://127.0.0.1',
                    raise_server_exceptions=False) as c:
        def forbidden(*args, **kwargs):
            pytest.fail('Missing FTS must never call Providers or credentials')
        c.app.state.service.agent_runtime.credentials.resolve = forbidden
        c.app.state.service.agent_runtime.adapters.require = forbidden
        yield c


def retain(c, bank, label, supersedes=None):
    request = body(label)
    if supersedes:
        request['facts'][0]['supersedes_fact_id'] = supersedes
    path = '/api/local/memory/banks/' + bank['id'] + '/retain'
    response = c.post(path, json=request, headers={'Idempotency-Key': label})
    assert response.status_code == 201, response.text
    return response.json(), request, path


def persistent(c):
    # total_changes counts rolled-back writes too; atomicity compares persisted rows.
    return snapshot(c)[1]


def test_missing_module_status_is_sanitized_and_matches_public_contract(unavailable):
    before = snapshot(unavailable)
    response = unavailable.get('/api/local/memory/runtime')
    assert response.status_code == 200
    state = response.json()
    assert state['keyword_index'] == {
        'engine': None, 'ready': False, 'error': 'FTS5_UNAVAILABLE',
        'rebuildable_from': 'canonical_active_facts',
    }
    assert state['semantic_retrieval']['runtime_enabled'] is False
    validate(unavailable, READS[0], state)
    assert snapshot(unavailable) == before


def test_missing_module_retain_dedup_replay_and_delete_never_touch_index(unavailable, fault):
    c = unavailable
    bank = post_bank(c, 'degraded71', 'bank71')
    offset = len(fault['calls'])
    result, request, path = retain(c, bank, 'zqalpha71')
    check(c, OPERATIONS[0], result)
    before = snapshot(c)
    replay = c.post(path, json=request, headers={'Idempotency-Key': 'zqalpha71'})
    assert replay.json() == result and replay.status_code == 201
    assert snapshot(c) == before
    duplicate = c.post(path, json=request, headers={'Idempotency-Key': 'dedup71'})
    assert duplicate.status_code == 201 and duplicate.json()['deduplicated'] is True
    source = result['source']['id']
    deleted = c.delete('/api/local/memory/sources/' + source, headers={'Idempotency-Key': 'delete71'})
    assert deleted.status_code == 200, deleted.text
    check(c, OPERATIONS[2], deleted.json())
    for key in ['zqalpha71', 'dedup71']:
        before = snapshot(c)
        response = c.post(path, json=request, headers={'Idempotency-Key': key})
        assert response.status_code == 409
        assert response.json()['error']['code'] == 'MEMORY_RECEIPT_UNAVAILABLE'
        assert snapshot(c) == before
    assert not any('memory_fact_fts' in q for q in fault['calls'][offset:])


def test_missing_module_supersede_retract_scope_and_context(unavailable):
    c = unavailable
    bank = post_bank(c, 'lifecycle71', 'life-bank71')
    other = post_bank(c, 'other71', 'other-bank71')
    old, _, _ = retain(c, bank, 'zqold71')
    replacement, _, _ = retain(c, bank, 'zqnew71', old['facts'][0]['id'])
    retain(c, other, 'zqother71')
    base = '/api/local/memory/banks/' + bank['id']
    before = snapshot(c)
    for query, expected in [('zqold71', []), ('zqother71', []), ('zqnew71', [replacement['facts'][0]['id']])]:
        response = c.post(base + ':recall', json={'query': query})
        assert response.status_code == 200
        assert [e['evidence_id'] for e in response.json()['evidence']] == expected
    context = c.post(base + ':context', json={'query': 'zqnew71'})
    assert context.status_code == 503 and context.json()['error']['code'] == 'MEMORY_INDEX_UNAVAILABLE'
    detail = c.post(base + ':recall-details', json={'evidence_ids': [replacement['facts'][0]['id']]})
    assert detail.status_code == 200 and len(detail.json()['details']) == 1
    assert snapshot(c) == before
    retracted = c.post('/api/local/memory/sources/' + replacement['source']['id'] + ':retract',
                       json={}, headers={'Idempotency-Key': 'retract71'})
    assert retracted.status_code == 200
    assert c.post(base + ':recall', json={'query': 'zqnew71'}).json()['evidence'] == []


@pytest.mark.parametrize('field', ['source.occurred_at', 'fact.occurred_at', 'fact.valid_to'])
def test_degraded_scan_keeps_temporal_filters(unavailable, field):
    c = unavailable
    bank = post_bank(c, 'time71', 'time-bank71')
    request = body('zqtime71')
    owner, name = field.split('.')
    target = request['source'] if owner == 'source' else request['facts'][0]
    target[name] = '2020-01-01T00:00:00Z' if name == 'valid_to' else '2100-01-01T00:00:00Z'
    path = '/api/local/memory/banks/' + bank['id']
    result = c.post(path + '/retain', json=request, headers={'Idempotency-Key': 'time71'})
    assert result.status_code == 201, result.text
    before = snapshot(c)
    response = c.post(path + ':recall', json={'query': 'zqtime71'})
    assert response.status_code == 200 and response.json()['evidence'] == []
    assert snapshot(c) == before


@pytest.mark.parametrize('error', [
    sql_error('database is locked', sqlite3.SQLITE_BUSY),
    sql_error('attempt to write a readonly database', sqlite3.SQLITE_READONLY),
    sql_error('near PRIVATE: syntax error'),
    sql_error('no such module: fts5 PRIVATE'),
    sql_error(code=sqlite3.SQLITE_BUSY),
    RuntimeError('PRIVATE program failure'),
], ids=['locked', 'readonly', 'syntax', 'near-match', 'wrong-code', 'program'])
def test_creation_errors_other_than_exact_absence_propagate(tmp_path, fault, error):
    store = Store(tmp_path / 'start.db')
    fail(fault, 'CREATE VIRTUAL TABLE', error)
    try:
        with pytest.raises(type(error)) as caught:
            MemoryPlane(store)
        assert caught.value is error
        assert not store.db.in_transaction
        assert store.db.execute("SELECT name FROM sqlite_master WHERE name='memory_fact_fts'").fetchone() is None
    finally:
        store.db.close()


@pytest.mark.parametrize('phase', ['DELETE FROM memory_fact_fts', 'SELECT fact_id FROM memory_fact_fts'])
def test_missing_module_message_outside_creation_is_not_a_degradation(client, fault, phase):
    plane = client.app.state.service.memory
    before = persistent(client)
    fail(fault, phase)
    with pytest.raises(sqlite3.OperationalError, match='no such module: fts5'):
        plane._ensure_keyword_index()
    fail(fault, None)
    assert persistent(client) == before


def test_existing_index_cannot_degrade_even_with_exact_creation_error(client, fault):
    plane = client.app.state.service.memory
    before = persistent(client)
    fail(fault, 'CREATE VIRTUAL TABLE')
    with pytest.raises(sqlite3.OperationalError, match='no such module: fts5'):
        plane._ensure_keyword_index()
    fail(fault, None)
    assert persistent(client) == before


@pytest.mark.parametrize('object_type', ['view', 'table'])
def test_wrong_named_object_is_not_a_healthy_index(client, object_type):
    store = client.app.state.service.store
    with store.transaction() as db:
        db.execute('DROP TABLE memory_fact_fts')
        if object_type == 'view':
            db.execute("CREATE VIEW memory_fact_fts AS SELECT 'id' AS fact_id, 'bank' AS bank_id, 'term' AS terms")
        else:
            db.execute('CREATE TABLE memory_fact_fts(fact_id,bank_id,terms)')
            db.execute("INSERT INTO memory_fact_fts VALUES('id','bank','term')")
    before = persistent(client)
    with pytest.raises(sqlite3.OperationalError):
        MemoryPlane(store)
    assert persistent(client) == before


@pytest.mark.parametrize('route', [':recall', ':context'])
@pytest.mark.parametrize('message', ['database is locked', 'no such table: memory_fact_fts', 'PRIVATE invalid query'])
def test_runtime_query_fault_is_500_not_scan_or_empty(client, fault, route, message):
    bank = post_bank(client, 'query71', 'query-bank71')
    retain(client, bank, 'zqquery71')
    before = snapshot(client)
    fail(fault, 'SELECT fact_id FROM memory_fact_fts', sql_error(message))
    result = client.post('/api/local/memory/banks/' + bank['id'] + route, json={'query': 'zqquery71'})
    assert result.status_code == 500, result.text
    assert result.json()['error']['code'] == 'INTERNAL_ERROR'
    assert 'PRIVATE' not in result.text
    fail(fault, None)
    assert snapshot(client) == before


def test_real_runtime_projection_loss_fails_read_and_write_without_canonical_loss(client):
    bank = post_bank(client, 'lost71', 'lost-bank71')
    first, _, path = retain(client, bank, 'zqlost71')
    store = client.app.state.service.store
    with store.transaction() as db:
        db.execute('DROP TABLE memory_fact_fts')
    before = persistent(client)
    for suffix in [':recall', ':context']:
        response = client.post(path.removesuffix('/retain') + suffix, json={'query': 'zqlost71'})
        assert response.status_code == 500, response.text
    request = body('zqnewlost71')
    response = client.post(path, json=request, headers={'Idempotency-Key': 'newlost71'})
    assert response.status_code == 500
    response = client.delete('/api/local/memory/sources/' + first['source']['id'],
                             headers={'Idempotency-Key': 'delete-lost71'})
    assert response.status_code == 500
    assert persistent(client) == before


@pytest.mark.parametrize('error', [sql_error('PRIVATE busy', sqlite3.SQLITE_BUSY), RuntimeError('PRIVATE fault')],
                         ids=['database', 'program'])
def test_degraded_canonical_failure_is_not_swallowed(unavailable, fault, error):
    c = unavailable
    bank = post_bank(c, 'canonical71', 'canonical-bank71')
    before = persistent(c)
    fail(fault, 'INSERT INTO memory_facts', error)
    path = '/api/local/memory/banks/' + bank['id'] + '/retain'
    response = c.post(path, json=body('zqcanonical71'), headers={'Idempotency-Key': 'canonical71'})
    assert response.status_code == 500 and 'PRIVATE' not in response.text
    fail(fault, None)
    assert persistent(c) == before
    assert c.post(path, json=body('zqcanonical71'), headers={'Idempotency-Key': 'canonical71'}).status_code == 201


@pytest.mark.parametrize('phase', ['INSERT INTO memory_fact_fts', 'DELETE FROM memory_fact_fts'])
def test_ready_index_write_failure_rolls_back_and_same_key_retries(client, fault, phase):
    bank = post_bank(client, 'atomic71', 'atomic-bank71')
    first, _, path = retain(client, bank, 'zqfirst71')
    before = persistent(client)
    if phase.startswith('INSERT'):
        request = body('zqsecond71')
        send = lambda: client.post(path, json=request, headers={'Idempotency-Key': 'retry71'})
        expected = 201
    else:
        send = lambda: client.delete('/api/local/memory/sources/' + first['source']['id'],
                                     headers={'Idempotency-Key': 'retry71'})
        expected = 200
    fail(fault, phase, sql_error('PRIVATE failed index'))
    result = send()
    assert result.status_code == 500 and 'PRIVATE' not in result.text
    fail(fault, None)
    assert persistent(client) == before
    assert send().status_code == expected
    after = snapshot(client)
    assert send().status_code == expected
    assert snapshot(client) == after


def test_ready_only_published_after_commit_and_failed_rebuild_keeps_previous_state(client, fault):
    plane = client.app.state.service.memory
    plane._fts_ready, plane._fts_error = False, 'FTS5_UNAVAILABLE'
    observations = []
    fault['before_commit'] = lambda: observations.append(plane._fts_ready)
    plane._ensure_keyword_index()
    fault['before_commit'] = None
    assert observations == [False] and plane._fts_ready is True
    fail(fault, 'COMMIT', sql_error('database is locked', sqlite3.SQLITE_BUSY))
    with pytest.raises(sqlite3.OperationalError, match='database is locked'):
        plane._ensure_keyword_index()
    fail(fault, None)
    assert plane._fts_ready is True
    assert not client.app.state.service.store.db.in_transaction


def test_restart_after_module_restored_rebuilds_only_active_facts(tmp_path, fault):
    path = tmp_path / 'restart71.db'
    fail(fault, 'CREATE VIRTUAL TABLE')
    with TestClient(create_app(path, False), base_url='http://127.0.0.1', raise_server_exceptions=False) as c:
        bank = post_bank(c, 'restart71', 'restart-bank71')
        old, _, _ = retain(c, bank, 'zqoldrestart71')
        keep, _, _ = retain(c, bank, 'zqkeeprestart71', old['facts'][0]['id'])
        retired, _, _ = retain(c, bank, 'zqretired71')
        deleted, _, _ = retain(c, bank, 'zqdeleted71')
        assert c.post('/api/local/memory/sources/' + retired['source']['id'] + ':retract',
                      json={}, headers={'Idempotency-Key': 'retired71'}).status_code == 200
        assert c.delete('/api/local/memory/sources/' + deleted['source']['id'],
                        headers={'Idempotency-Key': 'deleted71'}).status_code == 200
        before = persistent(c)
    fail(fault, None)
    for _ in range(2):
        with TestClient(create_app(path, False), base_url='http://127.0.0.1') as c:
            store = c.app.state.service.store
            assert c.get('/api/local/memory/runtime').json()['keyword_index']['ready'] is True
            with store.lock:
                indexed = [row[0] for row in store.db.execute('SELECT fact_id FROM memory_fact_fts')]
            assert indexed == [keep['facts'][0]['id']]
            current = persistent(c)
            for table, rows in before.items():
                assert current[table] == rows
            response = c.post('/api/local/memory/banks/' + bank['id'] + ':context', json={'query': 'zqkeeprestart71'})
            assert response.status_code == 200
            assert [e['evidence_id'] for e in response.json()['detail_catalog']] == indexed


def test_failed_memory_initialization_releases_store_and_lease_without_gc(tmp_path, monkeypatch):
    path = tmp_path / 'startup-failure.db'
    failure = RuntimeError('PRIVATE initialization failure')
    stores = []
    original = MemoryPlane._ensure_keyword_index
    def broken(self):
        stores.append(self.store)
        raise failure
    monkeypatch.setattr(MemoryPlane, '_ensure_keyword_index', broken)
    with pytest.raises(RuntimeError) as captured:
        with TestClient(create_app(path, False)):
            pytest.fail('Startup must fail')
    assert captured.value is failure
    with pytest.raises(sqlite3.ProgrammingError, match='closed'):
        stores[0].db.execute('SELECT 1')
    monkeypatch.setattr(MemoryPlane, '_ensure_keyword_index', original)
    # captured and failure retain their traceback, so GC cannot be the cleanup.
    with TestClient(create_app(path, False), base_url='http://127.0.0.1') as c:
        assert c.get('/api/local/memory/runtime').status_code == 200
