"""HA-0083: synthetic callbacks + actual SDK tests; never call real Providers."""
import json
import threading
from concurrent.futures import ThreadPoolExecutor

import pytest
from fastapi.testclient import TestClient

from backend.app import create_app
from backend.analysis import Problem
from backend.dsh_crossings import Crossings


@pytest.fixture
def setup(tmp_path, monkeypatch):
    monkeypatch.setenv('HARNESS_DSH_LOCAL', 'enabled')
    monkeypatch.setenv('HARNESS_DSH_RUN_ROOT', str(tmp_path / 'runs'))
    monkeypatch.delenv('HARNESS_DSH_REAL_ENABLED', raising=False)
    with TestClient(create_app(tmp_path / 'test.db', run_worker=False), base_url='http://localhost') as client:
        rt = client.app.state.service.dsh
        body = dict(objective='核对付款条件', document='SYNTH_CROSSING_SECRET：甲方验收后30天付款。',
                    public_data_confirmed=True, mode='integration_probe')
        ident = client.post('/api/local/dsh/runs', json=body,
                            headers={'Idempotency-Key': 'crossing'}).json()['initial_run']['id']
        check = lambda: rt.service.check(ident)
        yield rt, ident, Crossings(rt.store, ident, check)


def envelope(ident, value=None):
    return {'crossing_id': ident, 'request': value or {'messages': []}}


def model_result(*tools):
    return {'text': 'SYNTH_CROSSING_SECRET', 'usage': {}, 'tool_calls': [
        {'id': f'call_probe_{i}', 'name': name, 'arguments': json.dumps(args)}
        for i, (name, args) in enumerate(tools)]}


def issue(crossings, turn='m_1', name='read_clause', args=None):
    args = args or {'clause_id': 'clause-1'}
    reply = crossings.invoke('model', envelope(turn), lambda _: model_result((name, args)))
    return envelope(reply['value']['tool_calls'][0]['id'], {'name': name, 'arguments': args})


def test_replay_exact_mutation_safe_and_no_writes(setup):
    rt, ident, crossings = setup
    ticket = issue(crossings, name='submit_findings', args={'claim': 'SYNTH_CROSSING_SECRET'})
    calls = []
    def action(_):
        calls.append(1)
        return {'text': json.dumps({'accepted': False, 'submission_number': 1, 'notice': 'read clause-4'})}
    first = crossings.invoke('tool', ticket, action)
    changes = rt.store.db.total_changes
    replay = crossings.invoke('tool', ticket, action)
    assert replay == first and len(calls) == 1
    replay['text'] = 'modified'
    assert crossings.invoke('tool', ticket, action) == first
    assert rt.store.db.total_changes == changes
    rows = [dict(row) for row in rt.store.db.execute('SELECT * FROM dsh_crossings')]
    assert 'SYNTH_CROSSING_SECRET' not in json.dumps(rows)
    assert 'SYNTH_CROSSING_SECRET' not in json.dumps(rt.store.events(ident))
    assert 'read clause-4' not in json.dumps(rows)


def test_model_replay_and_tool_replay_concurrent(setup):
    rt, _, crossings = setup
    barrier = threading.Barrier(6)
    called = []
    def invoke(_):
        barrier.wait(timeout=5)
        return crossings.invoke('model', envelope('m_1'), lambda _: (
            called.append(1) or model_result(('read_clause', {'clause_id': 'clause-1'}))))
    with ThreadPoolExecutor(max_workers=6) as pool:
        results = list(pool.map(invoke, range(6)))
    assert all(r == results[0] for r in results) and len(called) == 1
    ticket = envelope(results[0]['value']['tool_calls'][0]['id'],
                      {'name': 'read_clause', 'arguments': {'clause_id': 'clause-1'}})
    def tool(_):
        barrier.wait(timeout=5)
        return crossings.invoke('tool', ticket, lambda _: called.append(2) or {'text': 'original'})
    with ThreadPoolExecutor(max_workers=6) as pool:
        assert list(pool.map(tool, range(6))) == [{'text': 'original'}] * 6
    assert called == [1, 2]


def test_same_raw_id_and_arguments_next_round_is_new_action(setup):
    rt, ident, crossings = setup
    first = issue(crossings)
    with pytest.raises(Problem, match='上一轮'):
        crossings.invoke('model', envelope('m_2'), lambda _: pytest.fail('unfinished predecessor'))
    calls = []
    crossings.invoke('tool', first, lambda _: calls.append(1) or {'text': 'one'})
    second = issue(crossings, 'm_2')
    assert second['crossing_id'] != first['crossing_id']
    crossings.invoke('tool', second, lambda _: calls.append(2) or {'text': 'two'})
    assert calls == [1, 2]
    rows = list(rt.store.db.execute("SELECT origin_id_sha256 FROM dsh_crossings WHERE kind='tool'"))
    assert rows[0][0] == rows[1][0]


@pytest.mark.parametrize('change', ['arguments', 'name', 'ticket', 'namespace', 'envelope'])
def test_conflict_or_forged_identity_never_executes(setup, change):
    _, _, crossings = setup
    request = issue(crossings)
    kind = 'tool'
    if change == 'arguments':
        request['request']['arguments']['clause_id'] = 'clause-2'
    elif change == 'name':
        request['request']['name'] = 'search_document'
    elif change == 'ticket':
        request['crossing_id'] = 'call_probe_0'
    elif change == 'namespace':
        kind = 'model'
    else:
        request['extra'] = True
    with pytest.raises(Problem):
        crossings.invoke(kind, request, lambda _: pytest.fail('must not execute'))


def test_other_generation_ticket_rejected(setup):
    rt, ident, crossings = setup
    ticket = issue(crossings)
    other = Crossings(rt.store, ident, lambda: rt.service.check(ident))
    with pytest.raises(Problem) as error:
        other.invoke('tool', ticket, lambda _: pytest.fail('cross-generation'))
    assert error.value.code == 'DSH_CROSSING_NOT_ISSUED'


def test_cancel_prevents_replay_without_duplicate_action(setup):
    rt, ident, crossings = setup
    ticket = issue(crossings)
    crossings.invoke('tool', ticket, lambda _: {'text': 'first'})
    rt.cancel(ident)
    changes = rt.store.db.total_changes
    with pytest.raises(Problem):
        crossings.invoke('tool', ticket, lambda _: pytest.fail('cancelled replay'))
    assert rt.store.db.total_changes == changes


def test_cancel_during_call_is_not_blocked_by_database_lock(setup):
    rt, ident, crossings = setup
    started, cancelled = threading.Event(), threading.Event()
    def action(_):
        started.set()
        assert cancelled.wait(5)
        return model_result()
    with ThreadPoolExecutor(max_workers=2) as pool:
        running = pool.submit(crossings.invoke, 'model', envelope('m_1'), action)
        assert started.wait(5)
        rt.cancel(ident)
        cancelled.set()
        with pytest.raises(Problem):
            running.result(timeout=5)
    assert rt.store.db.execute("SELECT status FROM dsh_crossings WHERE crossing_id='m_1'").fetchone()[0] == 'unknown'


def test_completion_commit_failure_does_not_repeat_action(setup):
    rt, ident, crossings = setup
    ticket = issue(crossings)
    rt.store.db.execute('''CREATE TEMP TRIGGER reject_receipt BEFORE UPDATE ON dsh_crossings
        WHEN NEW.kind='tool' AND NEW.status='completed' BEGIN SELECT RAISE(ABORT,'synthetic'); END''')
    calls = []
    with pytest.raises(Exception):
        crossings.invoke('tool', ticket, lambda _: calls.append(1) or {'text': 'done'})
    with pytest.raises(Problem):
        crossings.invoke('tool', ticket, lambda _: calls.append(2))
    assert calls == [1]
    row = rt.store.db.execute("SELECT status FROM dsh_crossings WHERE kind='tool'").fetchone()
    assert row[0] == 'unknown'


def test_receipt_event_atomicity_before_action(setup):
    rt, _, crossings = setup
    before = rt.store.db.execute('SELECT status FROM dsh_crossings').fetchone()[0]
    rt.store.db.execute('''CREATE TEMP TRIGGER reject_crossing BEFORE INSERT ON events
        WHEN NEW.doc LIKE '%dsh.crossing%' BEGIN SELECT RAISE(ABORT,'synthetic'); END''')
    with pytest.raises(Exception):
        crossings.invoke('model', envelope('m_1'), lambda _: pytest.fail('before commit'))
    assert rt.store.db.execute('SELECT status FROM dsh_crossings').fetchone()[0] == before == 'issued'


def test_restart_retains_unknown_and_never_resends(setup):
    rt, ident, crossings = setup
    rt.ledger.register_root(ident, 'a' * 64, 1000)
    rt.ledger.reserve(ident, 'call_1', binding_digest='a' * 64, request_digest='b' * 64,
                      input_bound=100, output_limit=100)
    rt.ledger.mark_sent(ident, 'call_1')
    rt.store.db.execute("UPDATE dsh_crossings SET status='in_flight' WHERE crossing_id='m_1'")
    rt.recover()
    assert rt.detail(ident)['run']['exit_reason'] == 'DSH_SERVER_RESTARTED'
    assert rt.store.db.execute('SELECT status FROM dsh_crossings').fetchone()[0] == 'unknown'
    assert rt.store.db.execute('SELECT status FROM business_budget_calls').fetchone()[0] == 'unknown'
    assert rt.ledger.snapshot(ident)['reserved'] == 200
    changes = rt.store.db.total_changes
    with pytest.raises(Problem):
        crossings.invoke('model', envelope('m_1'), lambda _: pytest.fail('restart resend'))
    assert rt.store.db.total_changes == changes


def test_completed_without_memory_never_executes(setup):
    _, _, crossings = setup
    crossings.invoke('model', envelope('m_1'), lambda _: model_result())
    crossings.responses.clear()
    with pytest.raises(Problem) as error:
        crossings.invoke('model', envelope('m_1'), lambda _: pytest.fail('lost cache'))
    assert error.value.code == 'DSH_CROSSING_UNAVAILABLE'


def test_actual_sdk_records_crossings_and_has_no_content(setup):
    rt, ident, unrelated = setup
    rt.execute(ident)
    detail = rt.detail(ident)
    assert detail['run']['status'] == 'succeeded', detail
    rows = [dict(row) for row in rt.store.db.execute(
        'SELECT * FROM dsh_crossings WHERE run_id=? AND generation!=?', (ident, unrelated.generation))]
    completed = [row for row in rows if row['status'] == 'completed']
    assert len([row for row in completed if row['kind'] == 'model']) == detail['budget']['calls'] == 2
    assert len([row for row in completed if row['kind'] == 'tool']) == 1
    assert not any(row['status'] in ('issued', 'in_flight') for row in rows)
    assert 'SYNTH_CROSSING_SECRET' not in json.dumps(rows)


def test_duplicate_execute_does_not_retire_active_generation(setup):
    rt, ident, crossings = setup
    with rt.store.transaction() as db:
        run = rt.store.get('runs', ident)
        run['status'] = 'running'
        rt.store.event(db, run, 'run.started', {})
    before = [tuple(row) for row in rt.store.db.execute('SELECT * FROM dsh_crossings')]
    rt.execute(ident)
    assert [tuple(row) for row in rt.store.db.execute('SELECT * FROM dsh_crossings')] == before


@pytest.mark.parametrize('template', ['free', 'payment_terms'])
def test_actual_sdk_retransmission_never_changes_budget_progress_or_submissions(setup, template):
    rt, ident, _ = setup
    if template == 'payment_terms':
        ident = rt.create(dict(objective='核对付款条件', document='第1条：甲方验收后30天付款。',
            public_data_confirmed=True, mode='integration_probe', template=template), 'payment')['initial_run']['id']
    original = rt.adapter.run
    observed = []
    def run(prompt, root, model, model_call, tool_call, emit, check, **kwargs):
        def twice(callback, kind):
            def call(body):
                first = callback(body)  # Pretend the first HTTP response was lost.
                before = rt.store.db.total_changes
                budget = rt.ledger.snapshot(ident)
                assert callback(body) == first
                assert rt.store.db.total_changes == before
                assert rt.ledger.snapshot(ident) == budget
                observed.append(kind)
                return first
            return call
        return original(prompt, root, model, twice(model_call, 'model'), twice(tool_call, 'tool'),
                        emit, check, **kwargs)
    rt.adapter.run = run
    rt.execute(ident)
    detail = rt.detail(ident)
    assert detail['run']['status'] == 'succeeded', detail
    events = rt.store.events(ident)
    success = next(e['data'] for e in events if e['event_type'] == 'run.succeeded')
    assert observed.count('model') == success['model_calls'] == detail['budget']['calls']
    assert observed.count('tool') == success['tool_calls']
    if template == 'payment_terms':
        checks = [e for e in events if e['event_type'] == 'dsh.findings.checked']
        assert len(checks) == 1
        assert checks[0]['data']['submission_number'] == 1


def test_real_loopback_gateway_replays_without_reexecution(setup, monkeypatch, tmp_path):
    # Synthetic child, real HTTP server/socket. Separate from the official SDK evidence above.
    import sys
    import adapters.dsh as adapter_module
    rt, ident, crossings = setup
    original = adapter_module.subprocess.Popen
    child = '''
import json, os, urllib.request
opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
def post(path, value):
    req = urllib.request.Request(os.environ['HARNESS_DSH_GATEWAY']+path,
        data=json.dumps(value).encode(), headers={'Authorization':'Bearer '+os.environ['HARNESS_DSH_CAPABILITY'],
        'Content-Type':'application/json'})
    with opener.open(req, timeout=10) as response:
        return json.load(response)
m = {'crossing_id':'m_1','request':{'messages':[]}}
first = post('/model', m)
assert post('/model', m) == first
t = {'crossing_id':first['value']['tool_calls'][0]['id'],
     'request':{'name':'read_clause','arguments':{'clause_id':'clause-1'}}}
response = post('/tool', t)
assert post('/tool', t) == response
print(json.dumps({'type':'result','text':'synthetic clause-1','session_sha256':'a'*64,
                  'turn_count':1,'runtime':'deepseek-harness@0.2.1-alpha.1'}),flush=True)
'''
    def spawn(argv, **kwargs):
        return original([sys.executable, '-c', child], **kwargs)
    monkeypatch.setattr(adapter_module.subprocess, 'Popen', spawn)
    calls = []
    def model(_):
        calls.append('model')
        return model_result(('read_clause', {'clause_id': 'clause-1'}))
    def tool(_):
        calls.append('tool')
        return {'text': 'first notice'}
    result = adapter_module.DshAdapter().run('synthetic', tmp_path / 'http-runs', 'synthetic',
        lambda body: crossings.invoke('model', body, model),
        lambda body: crossings.invoke('tool', body, tool), lambda _: None,
        lambda: rt.service.check(ident))
    assert result['text'] == 'synthetic clause-1'
    assert calls == ['model', 'tool']
