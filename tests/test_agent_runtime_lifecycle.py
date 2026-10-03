"""Zero-network lifecycle probes: failures must be attributable, not merely errors."""
import asyncio
import json

import pytest
from fastapi.testclient import TestClient

from backend import agent_runtime as runtime_module
from backend.agent_runtime import AgentRuntime, validate_contract
from backend.analysis import Problem
from backend.app import create_app
from backend.store import Store


class Adapter:
    def __init__(self, mode='normal'):
        self.mode, self.calls, self.closed = mode, 0, 0
        self.requests = []
        self.started, self.release = asyncio.Event(), asyncio.Event()

    def status_for(self, _):
        return 'supported'

    def require(self, _):
        return self

    async def stream(self, request):
        self.calls += 1
        self.requests.append(request)
        self.started.set()
        try:
            if self.mode == 'wait':
                await self.release.wait()
            if self.mode == 'empty':
                return
            yield 'first'
            if self.mode == 'wait_after_first':
                await self.release.wait()
            await asyncio.sleep(0)
            if self.mode == 'error':
                raise Problem('MODEL_PROVIDER_UNAVAILABLE', 'synthetic failure', 503)
            if self.mode == 'oversize':
                yield 'x' * 12000
            else:
                yield 'last'
        finally:
            self.closed += 1


class Credentials:
    def __init__(self):
        self.calls = 0

    def resolve(self, _):
        self.calls += 1
        return 'synthetic-test-value'


def setup_runtime(store, mode='normal'):
    adapter, credentials = Adapter(mode), Credentials()
    runtime = AgentRuntime(store, adapter, credentials, runtime_enabled=True)
    provider = runtime.create_provider({'name': 'probe', 'type': 'openai_compatible',
        'base_url': 'https://example.invalid', 'credential_ref': 'keychain://harnessagent/probe'}, 'provider')
    model = runtime.create_model({'provider_profile_id': provider['id'], 'display_name': 'probe',
        'model_id': 'synthetic', 'context_window': 4096}, 'model')
    agent = runtime.create_agent({'name': 'probe', 'description': '', 'system_prompt': 'test',
        'model_profile_id': model['id'], 'temperature': 0, 'max_output_tokens': 32, 'max_context_turns': 1}, 'agent')
    session = runtime.create_session({'agent_profile_id': agent['id']}, 'session')
    exchange = runtime.prepare_exchange(session['id'], {'content': 'original'}, 'send')
    return runtime, adapter, credentials, session, exchange


@pytest.fixture
def state(tmp_path):
    store = Store(tmp_path / 'lifecycle.db')
    try:
        yield setup_runtime(store)
    finally:
        store.close()


async def collect(iterator):
    result = [event async for event in iterator]
    for event in result:
        validate_contract('runtime_stream_event', event)
    return result


def assert_no_assistant(runtime, session):
    assert [m['role'] for m in runtime.store.runtime_messages(session['id'])] == ['user']


def test_cancelled_exchange_replay_has_no_provider_or_credential_call(state):
    runtime, adapter, credentials, session, exchange = state
    terminal = runtime.cancel_exchange(exchange['id'])
    events = asyncio.run(collect(runtime.stream_exchange(exchange['id'])))
    assert events[-1]['error_code'] == 'EXCHANGE_CANCELLED'
    assert adapter.calls == credentials.calls == 0
    assert runtime.store.runtime_get('runtime_chat_exchanges', exchange['id']) == terminal
    assert_no_assistant(runtime, session)


def test_duplicate_consumer_has_no_execution_or_cancellation_ownership(state):
    runtime, adapter, credentials, session, exchange = state
    adapter.mode = 'wait'

    async def scenario():
        owner = asyncio.create_task(collect(runtime.stream_exchange(exchange['id'])))
        await asyncio.wait_for(adapter.started.wait(), 1)
        # A different runtime instance shares the DB, not an in-memory lock.
        duplicate_runtime = AgentRuntime(runtime.store, adapter, credentials, runtime_enabled=True)
        duplicate = duplicate_runtime.stream_exchange(exchange['id'])
        try:
            event = await asyncio.wait_for(anext(duplicate), 1)
            assert event['error_code'] == 'EXCHANGE_IN_PROGRESS'
        finally:
            await duplicate.aclose()
            adapter.release.set()
        result = await asyncio.wait_for(owner, 1)
        assert result[-1]['type'] == 'done'

    asyncio.run(scenario())
    assert adapter.calls == credentials.calls == adapter.closed == 1
    assert len(runtime.store.runtime_messages(session['id'])) == 2


def test_busy_session_rejects_new_key_without_writing_and_replays_same_key(state):
    runtime, _, _, session, exchange = state
    assert runtime.prepare_exchange(session['id'], {'content': 'original'}, 'send') == exchange
    with pytest.raises(Problem) as error:
        runtime.prepare_exchange(session['id'], {'content': 'future'}, 'next')
    assert error.value.code == 'SESSION_BUSY'
    assert len(runtime.store.runtime_messages(session['id'])) == 1
    runtime.cancel_exchange(exchange['id'])
    assert runtime.prepare_exchange(session['id'], {'content': 'next'}, 'next')['status'] == 'queued'


@pytest.mark.parametrize('action', ['cancel', 'close'])
def test_cancel_or_close_after_delta_closes_provider_without_publishing(state, action):
    runtime, adapter, _, session, exchange = state

    async def scenario():
        stream = runtime.stream_exchange(exchange['id'])
        assert (await anext(stream))['type'] == 'delta'
        if action == 'cancel':
            runtime.cancel_exchange(exchange['id'])
            events = await collect(stream)
            assert [e['type'] for e in events] == ['error']
            assert events[0]['error_code'] == 'EXCHANGE_CANCELLED'
        await stream.aclose()

    asyncio.run(scenario())
    assert adapter.closed == 1
    assert runtime.store.runtime_get('runtime_chat_exchanges', exchange['id'])['status'] == 'cancelled'
    assert_no_assistant(runtime, session)


@pytest.mark.parametrize('action', ['persistent_cancel', 'task_cancel', 'timeout'])
def test_waiting_provider_is_released_without_another_delta(state, monkeypatch, action):
    runtime, adapter, _, session, exchange = state
    adapter.mode = 'wait'
    if action == 'timeout':
        monkeypatch.setattr(runtime_module, 'STREAM_TIMEOUT_SECONDS', .1, raising=False)

    async def scenario():
        task = asyncio.create_task(collect(runtime.stream_exchange(exchange['id'])))
        await asyncio.wait_for(adapter.started.wait(), 1)
        if action == 'task_cancel':
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task
        else:
            if action == 'persistent_cancel':
                runtime.cancel_exchange(exchange['id'])
            events = await asyncio.wait_for(task, .8)
            assert events[-1]['error_code'] == ('MODEL_PROVIDER_TIMEOUT' if action == 'timeout' else 'EXCHANGE_CANCELLED')

    asyncio.run(scenario())
    assert adapter.closed == 1
    assert_no_assistant(runtime, session)
    current = runtime.store.runtime_get('runtime_chat_exchanges', exchange['id'])
    assert current['status'] == ('failed' if action == 'timeout' else 'cancelled')


@pytest.mark.parametrize('mode,expected', [('empty', 'MODEL_EMPTY_RESPONSE'),
    ('error', 'MODEL_PROVIDER_UNAVAILABLE'), ('oversize', 'MODEL_OUTPUT_LIMIT')])
def test_failure_replay_preserves_counts_and_no_partial_assistant(state, mode, expected):
    runtime, adapter, credentials, session, exchange = state
    adapter.mode = mode
    first = asyncio.run(collect(runtime.stream_exchange(exchange['id'])))
    again = asyncio.run(collect(runtime.stream_exchange(exchange['id'])))
    assert first[-1]['error_code'] == again[-1]['error_code'] == expected
    assert first[-1]['model_calls'] == again[-1]['model_calls'] == 1
    assert adapter.calls == credentials.calls == adapter.closed == 1
    assert_no_assistant(runtime, session)


def test_success_replay_and_late_cancel_preserve_terminal_message(state):
    runtime, adapter, credentials, session, exchange = state
    first = asyncio.run(collect(runtime.stream_exchange(exchange['id'])))
    terminal = runtime.store.runtime_get('runtime_chat_exchanges', exchange['id'])
    assert runtime.cancel_exchange(exchange['id']) == terminal
    again = asyncio.run(collect(runtime.stream_exchange(exchange['id'])))
    assert first[-1]['message_id'] == again[-1]['message_id']
    assert adapter.calls == credentials.calls == 1
    assert len(runtime.store.runtime_messages(session['id'])) == 2


def test_restart_recovers_exchange_even_without_product_worker(tmp_path):
    path = tmp_path / 'restart.db'
    with TestClient(create_app(path, run_worker=False), base_url='http://127.0.0.1') as client:
        runtime, _, _, session, exchange = setup_runtime(client.app.state.service.store)
    with TestClient(create_app(path, run_worker=False), base_url='http://127.0.0.1') as client:
        detail = client.get('/api/local/agent-runtime/sessions/' + session['id']).json()
        assert detail['exchanges'][0]['status'] == 'failed'
        assert detail['exchanges'][0]['error_code'] == 'MODEL_RUNTIME_RESTARTED'
        assert [m['role'] for m in detail['messages']] == ['user']
        events = client.post('/api/local/agent-runtime/sessions/' + session['id'] + '/messages',
            headers={'Idempotency-Key': 'send', 'Accept': 'text/event-stream'}, json={'content': 'original'})
        assert 'MODEL_RUNTIME_RESTARTED' in events.text


def test_http_busy_and_cancelled_replay(tmp_path):
    with TestClient(create_app(tmp_path / 'http.db', run_worker=False), base_url='http://127.0.0.1') as client:
        runtime, adapter, credentials, session, exchange = setup_runtime(client.app.state.service.store)
        client.app.state.service.agent_runtime = runtime
        url = '/api/local/agent-runtime/sessions/' + session['id'] + '/messages'
        busy = client.post(url, headers={'Idempotency-Key': 'other', 'Accept': 'text/event-stream'}, json={'content': 'next'})
        assert busy.status_code == 409 and busy.json()['error']['code'] == 'SESSION_BUSY'
        runtime.cancel_exchange(exchange['id'])
        response = client.post(url, headers={'Idempotency-Key': 'send', 'Accept': 'text/event-stream'}, json={'content': 'original'})
        assert response.status_code == 200
        assert 'EXCHANGE_CANCELLED' in response.text
        assert adapter.calls == credentials.calls == 0


def test_http_disconnect_cancels_owner_and_closes_upstream(tmp_path):
    """Actual ASGI disconnect after a delta (TestClient buffers streams)."""
    app = create_app(tmp_path / 'disconnect.db', run_worker=False)

    async def scenario():
        async with app.router.lifespan_context(app):
            runtime, adapter, _, session, exchange = setup_runtime(app.state.service.store)
            adapter.mode = 'wait_after_first'
            app.state.service.agent_runtime = runtime
            disconnected = asyncio.Event()
            body = json.dumps({'content': 'original'}).encode()
            body_sent = False

            async def receive():
                nonlocal body_sent
                if not body_sent:
                    body_sent = True
                    return {'type': 'http.request', 'body': body, 'more_body': False}
                await disconnected.wait()
                return {'type': 'http.disconnect'}

            async def send(message):
                if message['type'] == 'http.response.body' and b'"delta"' in message.get('body', b''):
                    disconnected.set()

            scope = {'type': 'http', 'asgi': {'version': '3.0', 'spec_version': '2.0'},
                'http_version': '1.1', 'method': 'POST', 'scheme': 'http',
                'path': '/api/local/agent-runtime/sessions/' + session['id'] + '/messages',
                'raw_path': b'/', 'root_path': '', 'query_string': b'',
                'client': ('127.0.0.1', 12000), 'server': ('127.0.0.1', 80),
                'headers': [(b'host', b'127.0.0.1'), (b'content-type', b'application/json'),
                    (b'accept', b'text/event-stream'), (b'idempotency-key', b'send')]}
            await asyncio.wait_for(app(scope, receive, send), 2)
            assert adapter.closed == 1
            assert runtime.store.runtime_get('runtime_chat_exchanges', exchange['id'])['status'] == 'cancelled'
            assert_no_assistant(runtime, session)

    asyncio.run(scenario())


def test_restart_preserves_terminal_states_and_fails_streaming(state):
    runtime, adapter, credentials, session, exchange = state
    runtime.cancel_exchange(exchange['id'])
    cancelled = runtime.store.runtime_get('runtime_chat_exchanges', exchange['id'])
    next_exchange = runtime.prepare_exchange(session['id'], {'content': 'next'}, 'next')
    asyncio.run(collect(runtime.stream_exchange(next_exchange['id'])))
    success = runtime.store.runtime_get('runtime_chat_exchanges', next_exchange['id'])
    active = runtime.prepare_exchange(session['id'], {'content': 'active'}, 'active')
    claimed, owner = runtime._claim(active['id'])
    assert owner and claimed['status'] == 'streaming'
    runtime.recover()
    assert runtime.store.runtime_get('runtime_chat_exchanges', exchange['id']) == cancelled
    assert runtime.store.runtime_get('runtime_chat_exchanges', next_exchange['id']) == success
    assert runtime.store.runtime_get('runtime_chat_exchanges', active['id'])['error_code'] == 'MODEL_RUNTIME_RESTARTED'
    assert adapter.calls == credentials.calls == 1


def test_cancel_during_resolver_is_rechecked_before_transport(state):
    runtime, adapter, _, session, exchange = state

    class CancellingCredentials:
        def resolve(self, _):
            runtime.cancel_exchange(exchange['id'])
            return 'synthetic'

    runtime.credentials = CancellingCredentials()
    events = asyncio.run(collect(runtime.stream_exchange(exchange['id'])))
    assert events[-1]['error_code'] == 'EXCHANGE_CANCELLED'
    assert events[-1]['provider_calls'] == adapter.calls == 0
    assert_no_assistant(runtime, session)
