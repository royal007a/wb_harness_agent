"""Offline call-boundary tests; no Provider, Keychain or production DB access."""
import asyncio
from concurrent.futures import ThreadPoolExecutor
import json
import sqlite3
import threading
import time

import pytest

from backend.analysis import Problem
from backend.business_budget import BusinessTokenLedger, MAX_TOKENS, ModelCallResult, budgeted_model_call
from backend.store import Store


BINDING = 'a' * 64
DIGEST = 'b' * 64


@pytest.fixture
def ledger(tmp_path):
    store = Store(tmp_path / 'budget.db')
    item = BusinessTokenLedger(store)
    item.register_root('run_root', BINDING, 100)
    yield item
    store.db.close()


def reserve(ledger, call='call_1', member='run_root', amount=40, output=10, **kwargs):
    return ledger.reserve(member, call, binding_digest=kwargs.pop('binding_digest', BINDING),
                          request_digest=DIGEST, input_bound=amount, output_limit=output, **kwargs)


def usage(inputs=20, outputs=5):
    return {'input_tokens': inputs, 'output_tokens': outputs, 'total_tokens': inputs + outputs}


def fails(code, function, *args, **kwargs):
    with pytest.raises(Problem) as caught:
        function(*args, **kwargs)
    assert caught.value.code == code


def test_root_child_grandchild_share_limit_and_binding(ledger):
    ledger.bind_member('run_child', 'run_root')
    ledger.bind_member('run_grandchild', 'run_child')
    reserve(ledger, 'main')
    reserve(ledger, 'child', 'run_grandchild', purpose='child')
    assert ledger.snapshot('run_root')['remaining'] == 0
    fails('BUSINESS_TOKEN_BUDGET_EXHAUSTED', reserve, ledger, 'more', 'run_child')
    fails('BUSINESS_BUDGET_BINDING_MISMATCH', reserve, ledger, 'mismatch', binding_digest='c' * 64)
    fails('BUSINESS_BUDGET_ALREADY_REGISTERED', ledger.register_root, 'run_root', BINDING, 200)
    fails('BUSINESS_BUDGET_ALREADY_REGISTERED', ledger.register_root, 'run_child', BINDING, 200)
    ledger.register_root('run_other', BINDING, 100)
    fails('BUSINESS_BUDGET_ALREADY_REGISTERED', ledger.bind_member, 'run_child', 'run_other')
    assert ledger.snapshot('run_other')['remaining'] == 100


@pytest.mark.parametrize('value', [0, -1, True, False, 1.0, '100', None, MAX_TOKENS + 1])
def test_invalid_limits(ledger, value):
    fails('BUSINESS_BUDGET_INVALID_NUMBER', ledger.register_root, 'run_new', BINDING, value)


def test_exact_twenty_million_and_one_extra(ledger):
    ledger.register_root('run_large', BINDING)
    reserve(ledger, member='run_large', amount=MAX_TOKENS-1, output=1)
    assert ledger.snapshot('run_large')['remaining'] == 0
    fails('BUSINESS_TOKEN_BUDGET_EXHAUSTED', reserve, ledger, 'extra', 'run_large', 1, 1)


@pytest.mark.parametrize('field,value,code', [
    ('amount', True, 'BUSINESS_BUDGET_INVALID_NUMBER'),
    ('amount', -1, 'BUSINESS_BUDGET_INVALID_NUMBER'),
    ('output', 0, 'BUSINESS_BUDGET_INVALID_NUMBER'),
    ('call', 'unsafe\n', 'BUSINESS_BUDGET_INVALID_ID'),
    ('binding_digest', 'a'*64+'\n', 'BUSINESS_BUDGET_INVALID_DIGEST'),
    ('purpose', 'external', 'BUSINESS_BUDGET_INVALID_PURPOSE'),
    ('purpose', [], 'BUSINESS_BUDGET_INVALID_PURPOSE'),
])
def test_invalid_reservations_do_not_write(ledger, field, value, code):
    before = ledger.store.db.total_changes
    fails(code, reserve, ledger, **{field: value})
    assert ledger.store.db.total_changes == before


def test_atomic_reservation_competition(ledger):
    barrier = threading.Barrier(16)
    def attempt(i):
        barrier.wait()
        try:
            reserve(ledger, f'c{i}', amount=10, output=10)
            return 'ok'
        except Problem as exc:
            return exc.code
    with ThreadPoolExecutor(max_workers=16) as pool:
        result = list(pool.map(attempt, range(16)))
    assert result.count('ok') == 5
    assert result.count('BUSINESS_TOKEN_BUDGET_EXHAUSTED') == 11
    assert ledger.snapshot('run_root')['reserved'] == 100


def test_independent_connections_share_sqlite_reservation_lock(tmp_path):
    path = tmp_path / 'connections.db'
    stores = [Store(path) for _ in range(4)]
    ledgers = [BusinessTokenLedger(s) for s in stores]
    ledgers[0].register_root('run_root', BINDING, 100)
    barrier = threading.Barrier(4)
    def attempt(i):
        barrier.wait()
        try:
            reserve(ledgers[i], f'call_{i}')
            return 'ok'
        except Problem as exc:
            return exc.code
    try:
        with ThreadPoolExecutor(max_workers=4) as pool:
            result = list(pool.map(attempt, range(4)))
        assert result.count('ok') == 2
        assert result.count('BUSINESS_TOKEN_BUDGET_EXHAUSTED') == 2
        assert all(l.snapshot('run_root')['reserved'] == 100 for l in ledgers)
    finally:
        for store in stores:
            store.db.close()


def test_duplicate_calls_and_settlement_never_refund_twice(ledger):
    reserve(ledger)
    fails('BUSINESS_MODEL_CALL_ALREADY_USED', reserve, ledger)
    ledger.mark_sent('run_root', 'call_1')
    fails('BUSINESS_MODEL_CALL_STATE', ledger.mark_sent, 'run_root', 'call_1')
    ledger.settle('run_root', 'call_1', usage())
    snapshot = ledger.snapshot('run_root')
    assert (snapshot['spent'], snapshot['reserved'], snapshot['remaining']) == (25, 0, 75)
    fails('BUSINESS_MODEL_CALL_STATE', ledger.settle, 'run_root', 'call_1', usage())
    ledger.abandon('run_root', 'call_1')
    assert ledger.snapshot('run_root') == snapshot
    fails('BUSINESS_MODEL_CALL_ALREADY_USED', reserve, ledger)


@pytest.mark.parametrize('bad', [None, {}, usage(-1, 1), usage(True, 1),
    {'input_tokens': 5, 'output_tokens': 5, 'total_tokens': 11},
    {'input_tokens': 5.0, 'output_tokens': 5, 'total_tokens': 10}, usage(10**20, 0)])
def test_invalid_usage_persists_stop_instead_of_rolling_it_back(ledger, bad):
    reserve(ledger)
    ledger.mark_sent('run_root', 'call_1')
    fails('BUSINESS_MODEL_USAGE_INVALID', ledger.settle, 'run_root', 'call_1', bad)
    state = ledger.snapshot('run_root')
    assert state['status'] == 'usage_unknown'
    assert (state['spent'], state['reserved']) == (0, 50)
    fails('BUSINESS_BUDGET_STOPPED', reserve, ledger, 'retry')


@pytest.mark.parametrize('actual', [usage(41, 0), usage(20, 11), usage(100, 100)])
def test_breach_records_actual_not_fake_clamped_usage(ledger, actual):
    reserve(ledger)
    ledger.mark_sent('run_root', 'call_1')
    fails('BUSINESS_MODEL_USAGE_BREACH', ledger.settle, 'run_root', 'call_1', actual)
    state = ledger.snapshot('run_root')
    assert state['status'] == 'breached'
    assert state['spent'] == actual['total_tokens']
    fails('BUSINESS_BUDGET_STOPPED', reserve, ledger, 'next')


def test_unsent_refund_cannot_reuse_call_id(ledger):
    reserve(ledger)
    ledger.abandon('run_root', 'call_1')
    assert ledger.snapshot('run_root')['remaining'] == 100
    fails('BUSINESS_MODEL_CALL_ALREADY_USED', reserve, ledger)


def test_cancel_between_reservation_and_send(ledger):
    reserve(ledger)
    ledger.cancel('run_root')
    fails('BUSINESS_BUDGET_STOPPED', ledger.mark_sent, 'run_root', 'call_1')
    ledger.abandon('run_root', 'call_1')
    assert ledger.snapshot('run_root')['reserved'] == 0
    fails('BUSINESS_BUDGET_STOPPED', reserve, ledger, 'another')


def test_restart_and_explicit_recovery_are_conservative(tmp_path):
    path = tmp_path / 'restart.db'
    first = Store(path)
    ledger = BusinessTokenLedger(first)
    ledger.register_root('run_root', BINDING, 100)
    ledger.bind_member('run_child', 'run_root')
    reserve(ledger, 'a')
    reserve(ledger, 'b', member='run_child')
    ledger.mark_sent('run_root', 'a')
    first.db.close()
    second = Store(path)
    try:
        resumed = BusinessTokenLedger(second)
        assert resumed.snapshot('run_root')['reserved'] == 100
        resumed.recover('run_root')
        state = resumed.snapshot('run_root')
        assert state['status'] == 'usage_unknown'
        assert state['reserved'] == 50
        resumed.recover('run_root')
        assert resumed.snapshot('run_root') == state
        fails('BUSINESS_BUDGET_STOPPED', reserve, resumed, 'new', member='run_child')
    finally:
        second.db.close()


def test_recover_only_unsent_does_not_freeze_or_forget_call_id(ledger):
    reserve(ledger)
    ledger.recover('run_root')
    assert ledger.snapshot('run_root')['status'] == 'active'
    assert ledger.snapshot('run_root')['remaining'] == 100
    fails('BUSINESS_MODEL_CALL_ALREADY_USED', reserve, ledger)
    reserve(ledger, 'new')


def test_late_usage_cannot_unfreeze_recovered_root(ledger):
    reserve(ledger)
    ledger.mark_sent('run_root', 'call_1')
    ledger.recover('run_root')
    fails('BUSINESS_MODEL_CALL_STATE', ledger.settle, 'run_root', 'call_1', usage())
    assert ledger.snapshot('run_root')['status'] == 'usage_unknown'
    assert ledger.snapshot('run_root')['reserved'] == 50


def test_second_instance_does_not_recover_active_requests(ledger):
    reserve(ledger)
    ledger.mark_sent('run_root', 'call_1')
    other = BusinessTokenLedger(ledger.store)
    assert other.snapshot('run_root')['status'] == 'active'
    assert other.snapshot('run_root')['reserved'] == 50


def test_database_failure_does_not_commit_reservation(ledger):
    ledger.store.db.execute("""CREATE TRIGGER fail_call AFTER INSERT ON business_budget_calls
        BEGIN SELECT RAISE(ABORT,'synthetic failure'); END""")
    with pytest.raises(sqlite3.IntegrityError):
        reserve(ledger)
    assert ledger.snapshot('run_root')['calls'] == 0
    ledger.store.db.execute('DROP TRIGGER fail_call')
    reserve(ledger)
    assert ledger.snapshot('run_root')['reserved'] == 50


def invoke(ledger, send, **kwargs):
    return budgeted_model_call(ledger, member_id=kwargs.pop('member_id', 'run_root'),
        call_id=kwargs.pop('call_id', 'call_1'), binding_digest=BINDING,
        payload={'messages': [{'role': 'user', 'content': 'PRIVATE_SYNTHETIC'}]},
        input_counter=lambda body: 40, output_limit=10, send=send,
        timeout_seconds=kwargs.pop('timeout_seconds', 1), **kwargs)


def test_loop_calls_share_real_boundary_and_do_not_persist_text(ledger):
    async def scenario():
        called = []
        async def send(payload, output):
            assert output == 10
            assert payload['messages'][0]['content'] == 'PRIVATE_SYNTHETIC'
            called.append(1)
            return ModelCallResult({'tool_calls': [{'name': 'synthetic_tool'}]}, usage(40, 10))
        ledger.bind_member('run_child', 'run_root')
        first = await invoke(ledger, send)
        assert first['tool_calls'][0]['name'] == 'synthetic_tool'
        await invoke(ledger, send, call_id='child', member_id='run_child', purpose='child')
        with pytest.raises(Problem) as caught:
            await invoke(ledger, send, call_id='retry', purpose='retry')
        assert caught.value.code == 'BUSINESS_TOKEN_BUDGET_EXHAUSTED'
        assert len(called) == 2
        assert ledger.snapshot('run_root')['spent'] == 100
    asyncio.run(scenario())
    tables = ('business_budget_calls', 'business_budget_roots', 'business_budget_members')
    for table in tables:
        rows = [dict(row) for row in ledger.store.db.execute('SELECT * FROM ' + table)]
        assert 'PRIVATE_SYNTHETIC' not in json.dumps(rows)


@pytest.mark.parametrize('purpose', ['primary', 'child', 'retry', 'compaction', 'guard'])
def test_each_call_purpose_spends_same_root(ledger, purpose):
    async def send(*args):
        return ModelCallResult('candidate', usage())
    assert asyncio.run(invoke(ledger, send, purpose=purpose)) == 'candidate'
    assert ledger.snapshot('run_root')['spent'] == 25
    assert ledger.store.db.execute('SELECT purpose FROM business_budget_calls').fetchone()[0] == purpose


@pytest.mark.parametrize('timeout', [0, -1, True, '1', float('nan'), float('inf'), 3601])
def test_invalid_timeout_never_sends(ledger, timeout):
    async def send(*args):
        pytest.fail('invalid timeout must not send')
    with pytest.raises(Problem) as caught:
        asyncio.run(invoke(ledger, send, timeout_seconds=timeout))
    assert caught.value.code == 'BUSINESS_MODEL_INVALID_TIMEOUT'
    assert ledger.snapshot('run_root')['calls'] == 0


@pytest.mark.parametrize('count', [True, 0, -1, 1.0, 100])
def test_counter_failure_or_insufficient_headroom_is_before_transport(ledger, count):
    async def send(*args):
        pytest.fail('counter rejection must not send')
    with pytest.raises(Problem) as caught:
        asyncio.run(budgeted_model_call(ledger, member_id='run_root', call_id='first',
            binding_digest=BINDING, payload={'value': 'test'}, input_counter=lambda p: count,
            output_limit=10, send=send, timeout_seconds=1))
    expected = 'BUSINESS_TOKEN_BUDGET_EXHAUSTED' if type(count) is int and count == 100 else 'BUSINESS_BUDGET_INVALID_NUMBER'
    assert caught.value.code == expected
    assert ledger.snapshot('run_root')['calls'] == 0


def test_snapshot_of_payload_is_not_mutated_by_counter(ledger):
    body = {'value': 'original'}
    def counter(copy):
        copy['value'] = 'tampered'
        body['value'] = 'caller changed'
        return 40
    async def send(payload, output):
        assert payload == {'value': 'original'}
        return ModelCallResult('ok', usage())
    assert asyncio.run(budgeted_model_call(ledger, member_id='run_root', call_id='first',
        binding_digest=BINDING, payload=body, input_counter=counter,
        output_limit=10, send=send, timeout_seconds=1)) == 'ok'


def test_successful_call_replay_does_not_call_transport_again(ledger):
    called = []
    async def send(*args):
        called.append(1)
        return ModelCallResult('ok', usage())
    async def scenario():
        assert await invoke(ledger, send) == 'ok'
        with pytest.raises(Problem) as caught:
            await invoke(ledger, send)
        assert caught.value.code == 'BUSINESS_MODEL_CALL_ALREADY_USED'
    asyncio.run(scenario())
    assert len(called) == 1


def test_input_counter_exception_has_no_reservation_or_send(ledger):
    def counter(_):
        raise ValueError('tokenizer unavailable')
    async def send(*args):
        pytest.fail('must not send without counter')
    with pytest.raises(ValueError, match='tokenizer unavailable'):
        asyncio.run(budgeted_model_call(ledger, member_id='run_root', call_id='c',
            binding_digest=BINDING, payload={}, input_counter=counter,
            output_limit=10, send=send, timeout_seconds=1))
    assert ledger.snapshot('run_root')['calls'] == 0


def test_pending_call_ids_cannot_be_settled_under_another_root(ledger):
    ledger.register_root('run_other', BINDING, 100)
    reserve(ledger)
    ledger.mark_sent('run_root', 'call_1')
    fails('BUSINESS_MODEL_CALL_MISSING', ledger.settle, 'run_other', 'call_1', usage())
    assert ledger.snapshot('run_other')['spent'] == 0
    assert ledger.snapshot('run_root')['reserved'] == 50


@pytest.mark.parametrize('failure', ['exception', 'timeout', 'usage', 'shape', 'cancel', 'task_cancel'])
def test_transport_failure_freezes_and_never_retries(ledger, failure):
    async def scenario():
        called = 0
        closed = asyncio.Event()
        entered = asyncio.Event()
        cancel = asyncio.Event()
        async def send(payload, output):
            nonlocal called
            called += 1
            entered.set()
            try:
                if failure == 'exception':
                    raise RuntimeError('private provider error')
                if failure in {'timeout', 'cancel', 'task_cancel'}:
                    await asyncio.Event().wait()
                if failure == 'shape':
                    return {'untrusted': 'response'}
                return ModelCallResult('candidate', None)
            finally:
                closed.set()
        task = asyncio.create_task(invoke(ledger, send, timeout_seconds=0.03, cancel_event=cancel))
        if failure in {'cancel', 'task_cancel'}:
            await entered.wait()
            if failure == 'cancel':
                cancel.set()
            else:
                task.cancel()
        with pytest.raises((Problem, RuntimeError, TimeoutError, asyncio.CancelledError)):
            await task
        assert closed.is_set()
        assert ledger.snapshot('run_root')['status'] == 'usage_unknown'
        assert ledger.snapshot('run_root')['reserved'] == 50
        with pytest.raises(Problem) as caught:
            await invoke(ledger, send, call_id='next')
        assert caught.value.code == 'BUSINESS_BUDGET_STOPPED'
        assert called == 1
    asyncio.run(scenario())


def test_pre_cancel_has_no_reservation_or_send(ledger):
    async def scenario():
        cancel = asyncio.Event()
        cancel.set()
        async def send(*args):
            pytest.fail('must not send')
        with pytest.raises(asyncio.CancelledError):
            await invoke(ledger, send, cancel_event=cancel)
        assert ledger.snapshot('run_root')['calls'] == 0
    asyncio.run(scenario())


def test_root_cancelled_during_send_accounts_but_does_not_publish(ledger):
    async def scenario():
        async def send(payload, output):
            ledger.cancel('run_root')
            return ModelCallResult('must not publish', usage())
        with pytest.raises(Problem) as caught:
            await invoke(ledger, send)
        assert caught.value.code == 'BUSINESS_BUDGET_STOPPED'
        assert ledger.snapshot('run_root')['spent'] == 25
        assert ledger.snapshot('run_root')['status'] == 'cancelled'
    asyncio.run(scenario())


def test_cancel_after_mark_sent_but_before_dispatch_does_not_send(ledger, monkeypatch):
    original = ledger.mark_sent
    def cancel_on_dispatch(root_id, call_id):
        original(root_id, call_id)
        ledger.cancel(root_id)
    monkeypatch.setattr(ledger, 'mark_sent', cancel_on_dispatch)
    async def send(*args):
        pytest.fail('cancelled root must not dispatch queued callback')
    with pytest.raises(Problem) as caught:
        asyncio.run(invoke(ledger, send))
    assert caught.value.code == 'BUSINESS_BUDGET_STOPPED'
    assert ledger.snapshot('run_root')['status'] == 'cancelled'


def test_noncooperative_transport_cannot_hold_timeout_or_publish_late_result(ledger):
    async def scenario():
        release = asyncio.Event()
        finished = asyncio.Event()
        async def send(payload, output):
            try:
                await asyncio.Event().wait()
            except asyncio.CancelledError:
                await release.wait()
                finished.set()
                return ModelCallResult('late', usage())
        start = time.monotonic()
        try:
            with pytest.raises(TimeoutError):
                await invoke(ledger, send, timeout_seconds=0.01)
            assert time.monotonic() - start < 0.5
            assert ledger.snapshot('run_root')['status'] == 'usage_unknown'
        finally:
            release.set()
            await asyncio.wait_for(finished.wait(), 1)
        assert ledger.snapshot('run_root')['spent'] == 0
        assert ledger.snapshot('run_root')['reserved'] == 50
    asyncio.run(scenario())
