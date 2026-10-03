"""Real protocol adapter, synthetic HTTP only; no Provider or Keychain access."""
import asyncio
import json

import httpx
import pytest
from fastapi.testclient import TestClient

from backend import provider_adapters as providers
from backend import agent_runtime as runtime_module
from backend.agent_runtime import AgentRuntime, validate_contract
from backend.analysis import Problem
from backend.app import create_app
from backend.store import Store


def frame(value):
    return ('data: ' + json.dumps(value, ensure_ascii=False) + '\n\n').encode()


def chunk(content=None, finish=None, **delta):
    return {'id': 'chatcmpl-fixture', 'object': 'chat.completion.chunk',
            'choices': [{'index': 0, 'delta': {'content': content, **delta}, 'finish_reason': finish}]}


DELTA = frame(chunk('半段答案'))
STOP = frame(chunk(finish='stop'))
DONE = b'data: [DONE]\n\n'
REQUEST = providers.ProviderRequest('https://example.invalid/v1', 'synthetic-credential',
    'synthetic', 'test', ({'role': 'user', 'content': 'question'},), 0, 32)


@pytest.fixture
def wire(monkeypatch):
    original = httpx.AsyncClient
    def install(body, *, status=200, content_type='text/event-stream', exception=None, hang=False):
        record = {'requests': [], 'closed': 0, 'waiting': asyncio.Event()}
        class Stream(httpx.AsyncByteStream):
            async def __aiter__(self):
                for part in ([body] if isinstance(body, bytes) else body):
                    yield part
                if hang:
                    record['waiting'].set()
                    await asyncio.Event().wait()
                if exception:
                    raise exception
            async def aclose(self):
                record['closed'] += 1
        def handle(request):
            assert request.url.host == 'example.invalid'
            record['requests'].append(request)
            return httpx.Response(status, headers={'Content-Type': content_type}, stream=Stream())
        def client(**kwargs):
            assert kwargs['follow_redirects'] is False and kwargs['trust_env'] is False
            return original(transport=httpx.MockTransport(handle), **kwargs)
        monkeypatch.setattr(providers.httpx, 'AsyncClient', client)
        return record
    return install


async def collect(stream):
    return [item async for item in stream]


def make_runtime(store):
    class Credentials:
        calls = 0
        def resolve(self, _):
            self.calls += 1
            return REQUEST.credential
    credentials = Credentials()
    runtime = AgentRuntime(store, providers.ProviderAdapterRegistry(), credentials, runtime_enabled=True)
    provider = runtime.create_provider({'name': 'synthetic', 'type': 'openai_compatible',
        'base_url': REQUEST.base_url, 'credential_ref': 'keychain://harnessagent/synthetic'}, 'provider')
    model = runtime.create_model({'provider_profile_id': provider['id'], 'display_name': 'synthetic',
        'model_id': 'synthetic', 'context_window': 4096}, 'model')
    agent = runtime.create_agent({'name': 'synthetic', 'description': '', 'system_prompt': 'test',
        'model_profile_id': model['id'], 'temperature': 0, 'max_output_tokens': 32, 'max_context_turns': 1}, 'agent')
    session = runtime.create_session({'agent_profile_id': agent['id']}, 'session')
    return runtime, credentials, session


@pytest.mark.parametrize('ending,expected', [
    (b'', 'MODEL_PROVIDER_INCOMPLETE_STREAM'),
    (DONE, 'MODEL_PROVIDER_INCOMPLETE_STREAM'),
    (STOP, 'MODEL_PROVIDER_INCOMPLETE_STREAM'),
    (frame(chunk(finish='length')) + DONE, 'MODEL_OUTPUT_TRUNCATED'),
])
def test_protocol_failure_never_publishes_or_retries(tmp_path, wire, ending, expected):
    record = wire(DELTA + ending)
    store = Store(tmp_path / 'protocol.db')
    try:
        runtime, credentials, session = make_runtime(store)
        exchange = runtime.prepare_exchange(session['id'], {'content': 'question'}, 'send')
        events = asyncio.run(collect(runtime.stream_exchange(exchange['id'])))
        assert [event['type'] for event in events] == ['delta', 'error']
        assert events[-1]['error_code'] == expected
        for event in events:
            validate_contract('runtime_stream_event', event)
        detail = runtime.session_detail(session['id'])
        assert [m['role'] for m in detail['messages']] == ['user']
        assert detail['exchanges'][0]['status'] == 'failed'
        assert detail['exchanges'][0]['assistant_message_id'] is None
        replay = asyncio.run(collect(runtime.stream_exchange(exchange['id'])))
        assert replay == [events[-1]]
        assert credentials.calls == len(record['requests']) == record['closed'] == 1
        assert REQUEST.credential not in json.dumps(detail)
    finally:
        store.close()


@pytest.mark.parametrize('ending,expected', [
    (frame(chunk(finish='content_filter')), 'MODEL_PROVIDER_FILTERED'),
    (frame(chunk(finish='tool_calls')), 'MODEL_PROVIDER_UNSUPPORTED_OUTPUT'),
    (frame(chunk(finish='function_call')), 'MODEL_PROVIDER_UNSUPPORTED_OUTPUT'),
    (frame(chunk(tool_calls=[{'index': 0}])), 'MODEL_PROVIDER_UNSUPPORTED_OUTPUT'),
    (frame(chunk(function_call={'name': 'unexpected'})), 'MODEL_PROVIDER_UNSUPPORTED_OUTPUT'),
    (frame(chunk(refusal='upstream-sensitive-refusal')), 'MODEL_PROVIDER_REFUSED'),
    (frame({'error': {'message': 'upstream-sensitive-error'}}), 'MODEL_PROVIDER_REJECTED'),
    (b'data: invalid-json\n\n', 'MODEL_PROVIDER_INVALID_RESPONSE'),
    (frame(None), 'MODEL_PROVIDER_INVALID_RESPONSE'),
    (frame({'choices': []}), 'MODEL_PROVIDER_INVALID_RESPONSE'),
    (frame(chunk(content=123)), 'MODEL_PROVIDER_INVALID_RESPONSE'),
    (frame(chunk(finish='unknown')), 'MODEL_PROVIDER_INVALID_RESPONSE'),
    (frame({**chunk('mixed-id'), 'id': 'different'}), 'MODEL_PROVIDER_INVALID_RESPONSE'),
    (frame({**chunk('wrong-object'), 'object': 'chat.completion'}), 'MODEL_PROVIDER_INVALID_RESPONSE'),
    (frame(chunk(role='user')), 'MODEL_PROVIDER_INVALID_RESPONSE'),
    (STOP + frame(chunk('after stop')), 'MODEL_PROVIDER_INVALID_RESPONSE'),
    (STOP + STOP, 'MODEL_PROVIDER_INVALID_RESPONSE'),
    (b'data: \xff\n\n', 'MODEL_PROVIDER_INVALID_RESPONSE'),
])
def test_adapter_rejects_partial_malformed_or_unsupported_output(wire, ending, expected):
    record = wire(DELTA + ending + STOP + DONE)
    with pytest.raises(Problem) as error:
        asyncio.run(collect(providers.OpenAIChatCompletionsAdapter().stream(REQUEST)))
    assert error.value.code == expected
    assert 'upstream-sensitive' not in error.value.message
    assert record['closed'] == len(record['requests']) == 1


@pytest.mark.parametrize('newline', [b'\n', b'\r\n', b'\r'])
def test_success_accepts_fragmented_utf8_comments_multiline_and_usage(wire, newline):
    usage = {'id': 'chatcmpl-fixture', 'object': 'chat.completion.chunk',
             'choices': [], 'usage': {'total_tokens': 12}}
    # Whitespace after a JSON comma may cross SSE data lines.
    multiline = DELTA.replace(b', "object"', b',\ndata: "object"')
    body = b'\xef\xbb\xbf: heartbeat\n\nevent: message\n' + multiline + STOP + frame(usage) + DONE
    body = body.replace(b'\n', newline)
    record = wire([bytes([value]) for value in body])
    assert asyncio.run(collect(providers.OpenAIChatCompletionsAdapter().stream(REQUEST))) == ['半段答案']
    assert record['closed'] == 1
    sent = json.loads(record['requests'][0].content)
    assert sent['stream'] is True and sent['messages'][0]['role'] == 'system'


@pytest.mark.parametrize('choice', [
    {'index': 1, 'delta': {'content': 'wrong'}},
    {'index': False, 'delta': {'content': 'wrong'}},
    {'index': 0, 'delta': None},
    {'index': 0, 'delta': []},
])
def test_choice_shape_is_checked(wire, choice):
    item = chunk()
    item['choices'] = [choice]
    wire(frame(item) + STOP + DONE)
    with pytest.raises(Problem) as error:
        asyncio.run(collect(providers.OpenAIChatCompletionsAdapter().stream(REQUEST)))
    assert error.value.code == 'MODEL_PROVIDER_INVALID_RESPONSE'


@pytest.mark.parametrize('status,content_type,exception,expected', [
    (200, 'application/json', None, 'MODEL_PROVIDER_INVALID_RESPONSE'),
    (401, 'text/event-stream', None, 'MODEL_PROVIDER_REJECTED'),
    (429, 'text/event-stream', None, 'MODEL_PROVIDER_REJECTED'),
    (500, 'text/event-stream', None, 'MODEL_PROVIDER_REJECTED'),
    (200, 'text/event-stream', httpx.ReadTimeout('private upstream'), 'MODEL_PROVIDER_TIMEOUT'),
    (200, 'text/event-stream', httpx.RemoteProtocolError('private upstream'), 'MODEL_PROVIDER_UNAVAILABLE'),
])
def test_transport_errors_are_structured_and_closed(wire, status, content_type, exception, expected):
    record = wire(DELTA, status=status, content_type=content_type, exception=exception)
    with pytest.raises(Problem) as error:
        asyncio.run(collect(providers.OpenAIChatCompletionsAdapter().stream(REQUEST)))
    assert error.value.code == expected and 'private upstream' not in error.value.message
    assert record['closed'] == 1


@pytest.mark.parametrize('body', [b':' + b'x' * (256 * 1024 + 1), (b':keepalive\n\n' * 200000)])
def test_wire_limits_also_bound_ignored_data(wire, body):
    wire(body + b'\n\n' + DELTA + STOP + DONE)
    with pytest.raises(Problem) as error:
        asyncio.run(collect(providers.OpenAIChatCompletionsAdapter().stream(REQUEST)))
    assert error.value.code == 'MODEL_PROVIDER_RESPONSE_LIMIT'


def test_close_after_delta_closes_actual_response_and_does_not_publish(tmp_path, wire):
    record = wire(DELTA + STOP + DONE)
    store = Store(tmp_path / 'cancel.db')
    try:
        runtime, _, session = make_runtime(store)
        exchange = runtime.prepare_exchange(session['id'], {'content': 'question'}, 'send')
        async def cancel():
            stream = runtime.stream_exchange(exchange['id'])
            assert (await anext(stream))['type'] == 'delta'
            await stream.aclose()
        asyncio.run(cancel())
        assert store.runtime_get('runtime_chat_exchanges', exchange['id'])['status'] == 'cancelled'
        assert [m['role'] for m in store.runtime_messages(session['id'])] == ['user']
        assert record['closed'] == 1
    finally:
        store.close()


@pytest.mark.parametrize('ending,terminal', [(b'', 'error'), (STOP + DONE, 'done'),
    (frame(chunk(finish='length')) + DONE, 'error'),
    (frame({'error': {'message': 'upstream-sensitive-error'}}), 'error')])
def test_http_uses_protocol_verdict_not_partial_text(tmp_path, wire, ending, terminal):
    record = wire(DELTA + ending)
    app = create_app(tmp_path / 'http.db', run_worker=False)
    with TestClient(app, base_url='http://127.0.0.1') as client:
        runtime, _, session = make_runtime(app.state.service.store)
        app.state.service.agent_runtime = runtime
        endpoint = f"/api/local/agent-runtime/sessions/{session['id']}/messages"
        response = client.post(endpoint, headers={'Idempotency-Key': 'http-send', 'Accept': 'text/event-stream'},
                               json={'content': 'question'})
        assert response.status_code == 200
        events = [json.loads(line[6:]) for line in response.text.splitlines() if line.startswith('data: ')]
        assert [e['type'] for e in events] == ['delta', terminal]
        detail = client.get(f"/api/local/agent-runtime/sessions/{session['id']}").json()
        assert [m['role'] for m in detail['messages']] == (['user', 'assistant'] if terminal == 'done' else ['user'])
        assert detail['exchanges'][0]['status'] == ('succeeded' if terminal == 'done' else 'failed')
        assert 'upstream-sensitive-error' not in response.text + json.dumps(detail)
        repeat = client.post(endpoint, headers={'Idempotency-Key': 'http-send', 'Accept': 'text/event-stream'},
                             json={'content': 'question'})
        assert repeat.status_code == 200
        repeated_events = [json.loads(line[6:]) for line in repeat.text.splitlines() if line.startswith('data: ')]
        assert repeated_events[-1] == events[-1]
        assert len(record['requests']) == record['closed'] == 1


@pytest.mark.parametrize('body,expected', [
    (DELTA + STOP + b'data: [DONE]', 'MODEL_PROVIDER_INCOMPLETE_STREAM'),
    (DELTA + STOP + b'data: [DONE]\n', 'MODEL_PROVIDER_INCOMPLETE_STREAM'),
    (DELTA + frame({**chunk(), 'choices': [chunk()['choices'][0]] * 2}), 'MODEL_PROVIDER_INVALID_RESPONSE'),
    (DELTA + frame(chunk('escaped-surrogate')).replace(b'escaped-surrogate', br'\ud800'), 'MODEL_PROVIDER_INVALID_RESPONSE'),
    (DELTA + frame(chunk(refusal=False)), 'MODEL_PROVIDER_INVALID_RESPONSE'),
    (DELTA + frame(chunk(tool_calls=0)), 'MODEL_PROVIDER_INVALID_RESPONSE'),
    (DELTA + STOP.replace(b'"finish_reason": "stop"', b'"finish_reason": "length", "finish_reason": "stop"') + DONE,
     'MODEL_PROVIDER_INVALID_RESPONSE'),
    (DELTA + STOP.replace(b'"content": null', b'"content": NaN') + DONE, 'MODEL_PROVIDER_INVALID_RESPONSE'),
])
def test_incomplete_frames_and_invalid_payload_types(wire, body, expected):
    wire(body)
    with pytest.raises(Problem) as error:
        asyncio.run(collect(providers.OpenAIChatCompletionsAdapter().stream(REQUEST)))
    assert error.value.code == expected


def test_stop_can_carry_last_text_and_content_type_parameters(wire):
    record = wire(frame(chunk('完整答案', 'stop')) + DONE, content_type='text/event-stream; charset=utf-8')
    assert asyncio.run(collect(providers.OpenAIChatCompletionsAdapter().stream(REQUEST))) == ['完整答案']
    assert record['closed'] == 1


def test_empty_normal_stream_is_not_a_successful_answer(tmp_path, wire):
    record = wire(STOP + DONE)
    store = Store(tmp_path / 'empty.db')
    try:
        runtime, _, session = make_runtime(store)
        exchange = runtime.prepare_exchange(session['id'], {'content': 'question'}, 'send')
        events = asyncio.run(collect(runtime.stream_exchange(exchange['id'])))
        assert events[-1]['error_code'] == 'MODEL_EMPTY_RESPONSE'
        assert record['closed'] == 1
        assert [m['role'] for m in store.runtime_messages(session['id'])] == ['user']
    finally:
        store.close()


@pytest.mark.parametrize('stop', ['cancel', 'timeout'])
def test_pending_actual_transport_is_closed_when_runtime_stops(tmp_path, wire, monkeypatch, stop):
    record = wire(DELTA, hang=True)
    store = Store(tmp_path / 'pending.db')
    if stop == 'timeout':
        monkeypatch.setattr(runtime_module, 'STREAM_TIMEOUT_SECONDS', .05)
    try:
        runtime, _, session = make_runtime(store)
        exchange = runtime.prepare_exchange(session['id'], {'content': 'question'}, 'send')
        async def scenario():
            pending = asyncio.create_task(collect(runtime.stream_exchange(exchange['id'])))
            await asyncio.wait_for(record['waiting'].wait(), 1)
            if stop == 'cancel':
                runtime.cancel_exchange(exchange['id'])
            return await asyncio.wait_for(pending, 2)
        events = asyncio.run(scenario())
        assert [e['type'] for e in events] == ['delta', 'error']
        assert events[-1]['error_code'] == ('EXCHANGE_CANCELLED' if stop == 'cancel' else 'MODEL_PROVIDER_TIMEOUT')
        assert record['closed'] == 1
        assert [m['role'] for m in store.runtime_messages(session['id'])] == ['user']
    finally:
        store.close()


def test_real_registry_still_respects_disabled_gate(tmp_path, wire):
    record = wire(DELTA + STOP + DONE)
    store = Store(tmp_path / 'gate.db')
    try:
        runtime, credentials, session = make_runtime(store)
        runtime._runtime_enabled = False
        exchange = runtime.prepare_exchange(session['id'], {'content': 'question'}, 'send')
        events = asyncio.run(collect(runtime.stream_exchange(exchange['id'])))
        assert events[0]['error_code'] == 'MODEL_RUNTIME_DISABLED'
        assert credentials.calls == len(record['requests']) == 0
    finally:
        store.close()


def test_large_ignored_batch_is_cooperative_not_quadratic(wire):
    wire(b'\n' * (1024 * 1024) + DELTA + STOP + DONE)
    async def scenario():
        ticks = []
        async def heartbeat():
            for _ in range(10):
                await asyncio.sleep(0)
                ticks.append(1)
        heartbeat_task = asyncio.create_task(heartbeat())
        stream = providers.OpenAIChatCompletionsAdapter().stream(REQUEST)
        assert await anext(stream) == '半段答案'
        # Non-data input processing must have yielded before its first text delta.
        assert len(ticks) == 10
        assert await collect(stream) == []
        await heartbeat_task
    asyncio.run(scenario())
