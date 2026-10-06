"""HA-0085: metadata lifecycle, failure windows and cancellation; synthetic only."""
import json
import sqlite3
import tempfile
import threading
from concurrent.futures import ThreadPoolExecutor

import pytest
from fastapi.testclient import TestClient

from backend.analysis import Problem
from backend.app import create_app
from backend.dsh_crossings import Crossings, retire
from test_dsh_crossings import envelope, issue, model_result


@pytest.fixture
def setup(tmp_path, monkeypatch):
    # Use a short, resolved root for SDK runtime files (macOS /var and /tmp are symlinks).
    from pathlib import Path
    with tempfile.TemporaryDirectory(prefix='h85-') as directory:
        monkeypatch.setenv('HARNESS_DSH_LOCAL', 'enabled')
        monkeypatch.setenv('HARNESS_DSH_RUN_ROOT', str(Path(directory).resolve() / 'runs'))
        monkeypatch.delenv('HARNESS_DSH_REAL_ENABLED', raising=False)
        with TestClient(create_app(tmp_path / 'test.db', run_worker=False), base_url='http://localhost') as client:
            rt = client.app.state.service.dsh
            ident = rt.create(dict(objective='核对付款条件', document='SYNTH_CROSSING_SECRET：甲方验收后30天付款。',
                public_data_confirmed=True, mode='integration_probe'), 'retirement')['initial_run']['id']
            yield rt, ident, Crossings(rt.store, ident, lambda: rt.service.check(ident))


def rows(rt, generation):
    return [dict(r) for r in rt.store.db.execute(
        'SELECT * FROM dsh_crossings WHERE generation=? ORDER BY crossing_id', (generation,))]


def events(rt, ident):
    return rt.store.events(ident)


def test_controlled_bridge_publication_sequence_without_sdk_startup(setup, monkeypatch):
    """Same platform callbacks; a synthetic bridge avoids conflating SDK startup with sequence faults."""
    rt, ident, _ = setup
    def adapter(prompt, root, model, model_call, tool_call, emit, check, **kwargs):
        messages = [{'role': 'user', 'content': [{'type': 'text', 'text': prompt}]}]
        def request():
            return {'model': model, 'purpose': 'primary', 'messages': messages,
                    'tools': [{'name': name, 'parameters': {'type': 'object'}}
                              for name in ('search_document', 'read_clause')]}
        first = model_call(envelope('m_1', request()))
        calls = first['value']['tool_calls']
        assert calls
        messages.append({'role': 'assistant', 'content': [dict(type='tool-call', **c) for c in calls]})
        for call in calls:
            output = tool_call(envelope(call['id'], {'name': call['name'], 'arguments': json.loads(call['arguments'])}))
            messages.append({'role': 'tool', 'toolCallId': call['id'],
                             'content': [{'type': 'text', 'text': output['text']}]})
        last = model_call(envelope(first['next_model_crossing'], request()))
        assert not last['value']['tool_calls']
        return {'type': 'result', 'text': last['value']['text'], 'session_sha256': 'a' * 64,
                'turn_count': 2, 'runtime': 'deepseek-harness@0.2.1-alpha.1'}
    monkeypatch.setattr(rt.adapter, 'run', adapter)
    rt.execute(ident)
    detail = rt.detail(ident)
    assert detail['budget']['calls'] == 2
    assert detail['run']['status'] == 'succeeded', detail['run']['exit_reason']
    log = events(rt, ident)
    assert log[-1]['event_type'] == 'run.succeeded'
    assert [e['sequence'] for e in log] == list(range(1, detail['run']['latest_sequence'] + 1))


def test_retirement_distinguishes_unused_unknown_and_historical(setup):
    rt, ident, crossings = setup
    ticket = issue(crossings)
    other = Crossings(rt.store, ident, lambda: rt.service.check(ident))
    rt.store.db.execute("UPDATE dsh_crossings SET status='in_flight' WHERE crossing_id=?",
                        (ticket['crossing_id'],))
    # A legacy failed receipt is preserved, not retrospectively interpreted as unused.
    rt.store.db.execute("UPDATE dsh_crossings SET status='failed' WHERE generation=?", (other.generation,))
    with rt.store.transaction() as db:
        retire(rt.store, db, ident, crossings.generation)
    result = {r['crossing_id']: r['status'] for r in rows(rt, crossings.generation)}
    assert result == {'m_1': 'completed', 'm_2': 'retired', ticket['crossing_id']: 'unknown'}
    assert rows(rt, other.generation)[0]['status'] == 'failed'
    before = rt.store.db.total_changes
    with rt.store.transaction() as db:
        retire(rt.store, db, ident)
    assert rt.store.db.total_changes == before
    assert 'SYNTH_CROSSING_SECRET' not in json.dumps(events(rt, ident))
    assert all(e['data'].get('schema_version') == 'dsh-crossing@2'
               for e in events(rt, ident) if e['event_type'] == 'dsh.crossing')


def test_retirement_does_not_touch_other_generation(setup):
    rt, ident, crossings = setup
    other = Crossings(rt.store, ident, lambda: rt.service.check(ident))
    with rt.store.transaction() as db:
        retire(rt.store, db, ident, crossings.generation)
    assert rows(rt, crossings.generation)[0]['status'] == 'retired'
    assert rows(rt, other.generation)[0]['status'] == 'issued'


def test_retirement_event_failure_rolls_back_all_receipts(setup, monkeypatch):
    rt, ident, crossings = setup
    issue(crossings)
    before_rows, before_events = rows(rt, crossings.generation), events(rt, ident)
    original, calls = rt.store.event, []
    def event(db, run, kind, data=None, step_id=None, **kwargs):
        result = original(db, run, kind, data, step_id, **kwargs)
        if kind == 'dsh.crossing':
            calls.append(data)
            if len(calls) == 2:
                raise sqlite3.OperationalError('synthetic audit fault')
        return result
    monkeypatch.setattr(rt.store, 'event', event)
    with pytest.raises(sqlite3.OperationalError):
        with rt.store.transaction() as db:
            retire(rt.store, db, ident, crossings.generation)
    assert rows(rt, crossings.generation) == before_rows
    assert events(rt, ident) == before_events


@pytest.mark.parametrize('template', ['free', 'payment_terms'])
def test_sdk_success_retires_before_terminal_in_one_transaction(setup, monkeypatch, template):
    rt, ident, unrelated = setup
    if template == 'payment_terms':
        ident = rt.create(dict(objective='核对付款条件', document='甲方验收后30天付款。',
            public_data_confirmed=True, mode='integration_probe', template=template),
            'retire-payment')['initial_run']['id']
    original, observed = rt.store.event, []
    def event(db, run, kind, data=None, step_id=None, **kwargs):
        if kind == 'run.succeeded':
            observed.append((db.in_transaction, [r[0] for r in db.execute(
                'SELECT status FROM dsh_crossings WHERE run_id=? AND generation!=?',
                (ident, unrelated.generation))]))
        return original(db, run, kind, data, step_id, **kwargs)
    monkeypatch.setattr(rt.store, 'event', event)
    rt.execute(ident)
    detail = rt.detail(ident)
    assert detail['run']['status'] == 'succeeded', detail
    assert len(observed) == 1 and observed[0][0]
    assert observed[0][1].count('retired') == 1
    assert set(observed[0][1]) == {'completed', 'retired'}
    log = events(rt, ident)
    assert log[-1]['event_type'] == 'run.succeeded'
    assert [e['sequence'] for e in log] == list(range(1, detail['run']['latest_sequence'] + 1))
    assert detail['budget']['reserved'] == 0
    if template == 'free':
        assert rows(rt, unrelated.generation)[0]['status'] == 'issued'


def test_normal_failure_retires_before_terminal(setup, monkeypatch):
    rt, ident, unrelated = setup
    # Failure after the SDK returns but before publication; no extra provider request.
    original = rt.adapter.run
    def adapter(*args, **kwargs):
        result = original(*args, **kwargs)
        return dict(result, text='没有证据引用')
    monkeypatch.setattr(rt.adapter, 'run', adapter)
    rt.execute(ident)
    detail = rt.detail(ident)
    assert detail['run']['exit_reason'] == 'DSH_EVIDENCE_CITATION_INVALID'
    assert detail['artifacts'] == []
    assert events(rt, ident)[-1]['event_type'] == 'run.failed'
    states = [r[0] for r in rt.store.db.execute(
        'SELECT status FROM dsh_crossings WHERE generation!=?', (unrelated.generation,))]
    assert 'retired' in states and set(states) <= {'completed', 'retired'}


def test_success_event_fault_rolls_back_publication_and_retirement(setup, monkeypatch):
    rt, ident, unrelated = setup
    original, observed = rt.store.event, []
    def event(db, run, kind, data=None, step_id=None, **kwargs):
        if kind in {'run.succeeded', 'run.failed'}:
            observed.append((kind, [r[0] for r in db.execute(
                "SELECT status FROM dsh_crossings WHERE kind='model' AND generation!=? ORDER BY model_round",
                (unrelated.generation,))]))
        value = original(db, run, kind, data, step_id, **kwargs)
        if kind == 'run.succeeded':
            raise sqlite3.OperationalError('synthetic after terminal write')
        return value
    monkeypatch.setattr(rt.store, 'event', event)
    rt.execute(ident)
    detail = rt.detail(ident)
    assert detail['run']['status'] == 'failed' and not detail['artifacts']
    assert [kind for kind, _ in observed] == ['run.succeeded', 'run.failed']
    assert all(states[-1] == 'retired' for _, states in observed)
    log = events(rt, ident)
    assert not any(e['event_type'] == 'run.succeeded' for e in log)
    retired = [e for e in log if e['event_type'] == 'dsh.crossing' and e['data']['status'] == 'retired']
    assert len(retired) == 1 and log[-1]['event_type'] == 'run.failed'


def test_failed_terminal_fault_does_not_commit_detached_retirement(setup, monkeypatch):
    rt, ident, unrelated = setup
    def adapter(*args, **kwargs):
        raise Problem('SYNTHETIC_FAILURE', 'synthetic', 500)
    monkeypatch.setattr(rt.adapter, 'run', adapter)
    original = rt.store.event
    def event(db, run, kind, data=None, step_id=None, **kwargs):
        value = original(db, run, kind, data, step_id, **kwargs)
        if kind == 'run.failed':
            raise sqlite3.OperationalError('synthetic terminal failure')
        return value
    monkeypatch.setattr(rt.store, 'event', event)
    with pytest.raises(sqlite3.OperationalError):
        rt.execute(ident)
    assert rt.detail(ident)['run']['status'] == 'running'
    states = [r[0] for r in rt.store.db.execute(
        'SELECT status FROM dsh_crossings WHERE generation!=?', (unrelated.generation,))]
    assert states == ['issued']
    assert not any(e['event_type'] == 'run.failed' for e in events(rt, ident))
    monkeypatch.setattr(rt.store, 'event', original)
    rt.recover()
    assert rt.detail(ident)['run']['exit_reason'] == 'DSH_SERVER_RESTARTED'
    assert set(r[0] for r in rt.store.db.execute('SELECT status FROM dsh_crossings')) == {'retired'}


def test_restart_unknown_budget_and_unused_retirement(setup):
    rt, ident, crossings = setup
    ticket = issue(crossings)
    rt.ledger.register_root(ident, 'a' * 64, 1000)
    rt.ledger.reserve(ident, 'call_1', binding_digest='a' * 64, request_digest='b' * 64,
                      input_bound=100, output_limit=100)
    rt.ledger.mark_sent(ident, 'call_1')
    rt.store.db.execute("UPDATE dsh_crossings SET status='in_flight' WHERE crossing_id=?", (ticket['crossing_id'],))
    rt.recover()
    assert {r['status'] for r in rows(rt, crossings.generation)} == {'completed', 'unknown', 'retired'}
    assert rt.ledger.snapshot(ident)['reserved'] == 200
    before = rt.store.db.total_changes
    rt.recover()
    assert rt.store.db.total_changes == before
    with pytest.raises(Problem):
        crossings.invoke('model', envelope('m_2'), lambda _: pytest.fail('restart resend'))


def test_cancel_does_not_wait_for_crossing_and_late_audit_is_honest(setup):
    rt, ident, crossings = setup
    entered, release = threading.Event(), threading.Event()
    def provider(_):
        entered.set()
        assert release.wait(5)
        return model_result()
    with ThreadPoolExecutor(max_workers=2) as pool:
        pending = pool.submit(crossings.invoke, 'model', envelope('m_1'), provider)
        assert entered.wait(5)
        try:
            cancelled = pool.submit(rt.cancel, ident).result(timeout=2)
            assert cancelled['status'] == 'cancelled'
        finally:
            release.set()
        with pytest.raises(Problem):
            pending.result(timeout=5)
    assert rows(rt, crossings.generation)[0]['status'] == 'unknown'
    log = events(rt, ident)
    cancel_seq = next(e['sequence'] for e in log if e['event_type'] == 'run.cancelled')
    assert log[-1]['sequence'] > cancel_seq and log[-1]['data']['status'] == 'unknown'
    assert rt.detail(ident)['run']['status'] == 'cancelled' and not rt.detail(ident)['artifacts']
