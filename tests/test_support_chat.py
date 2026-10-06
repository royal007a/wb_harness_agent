import asyncio
import json
import os

import httpx
import pytest
from fastapi.testclient import TestClient

from backend.app import create_app
from backend.analysis import Problem
from backend.store import Store
from backend.support_providers import SupportProviders
from backend.support_chat import SupportChat


class Stream(httpx.AsyncByteStream):
    def __init__(self, events):
        self.events = events
        self.closed = 0
    async def __aiter__(self):
        for event in self.events:
            yield (('data: ' + (event if isinstance(event, str) else json.dumps(event)) + '\n\n')).encode()
            await asyncio.sleep(0)
    async def aclose(self):
        self.closed += 1


def chunk(delta, reason=None):
    return {'id': 'completion-test', 'object': 'chat.completion.chunk',
            'choices': [{'index': 0, 'delta': delta, 'finish_reason': reason}]}


def frames(text='退款需要订单号。', *, tool=False):
    if tool:
        events = [chunk({'tool_calls': [{'index': 0, 'id': 'call_1', 'type': 'function',
                                       'function': {'name': 'lookup', 'arguments': '{"order":"123"}'}}]}, 'tool_calls')]
    else:
        events = [chunk({'role': 'assistant', 'content': text[:3]}), chunk({'content': text[3:]}, 'stop')]
    return events + [{'id': 'completion-test', 'choices': [], 'usage': {'prompt_tokens': 30, 'completion_tokens': 10}}, '[DONE]']


@pytest.fixture
def chat(tmp_path, monkeypatch):
    master = tmp_path / 'master'
    master.write_bytes(os.urandom(32))
    master.chmod(0o600)
    monkeypatch.setenv('HARNESS_SUPPORT', 'enabled')
    monkeypatch.setenv('HARNESS_SUPPORT_MASTER_KEY_FILE', str(master))
    store = Store(tmp_path / 'test.db')
    providers = SupportProviders(store)
    provider = providers.save({'name': 'test', 'api_key': 'synthetic-chat-secret', 'auto_probe': False})
    runtime = SupportChat(store, providers)
    runtime.provider_id = provider['id']
    yield runtime
    store.close()


def session(chat, **kw):
    a = chat.agent_save({'name': '客服', 'provider_id': chat.provider_id, **kw})
    return chat.create_session({'agent_id': a['id']})


async def collect(chat, ident):
    return [e async for e in chat.stream(ident)]


def transport(chat, result):
    calls, bodies = [], []
    def send(request):
        calls.append(request)
        body = Stream(result(len(calls)) if callable(result) else result)
        bodies.append(body)
        return httpx.Response(200, headers={'content-type': 'text/event-stream'}, stream=body)
    chat.providers.transport = httpx.MockTransport(send)
    return calls, bodies


def test_multi_turn_stream_persistence_idempotency(chat):
    s = session(chat)
    calls, bodies = transport(chat, frames())
    one = chat.begin(s['id'], {'content': '如何退款？'}, 'key1')
    events = asyncio.run(collect(chat, one['id']))
    assert [e['type'] for e in events] == ['start', 'delta', 'delta', 'done']
    assert events[-1]['budget']['spent'] == 40 and events[-1]['budget']['reserved'] == 0
    detail = chat.detail(s['id'])
    assert [m['role'] for m in detail['messages']] == ['user', 'assistant']
    assert detail['messages'][-1]['content'] == '退款需要订单号。'
    replay = chat.begin(s['id'], {'content': '如何退款？'}, 'key1')
    assert asyncio.run(collect(chat, replay['id']))[0]['replayed'] is True
    assert len(calls) == 1 and bodies[0].closed == 1
    two = chat.begin(s['id'], {'content': '订单号是123'}, 'key2')
    assert asyncio.run(collect(chat, two['id']))[-1]['type'] == 'done'
    assert [m['role'] for m in json.loads(calls[-1].content)['messages']] == ['system', 'user', 'assistant', 'user']
    assert 'synthetic-chat-secret' not in json.dumps(chat.detail(s['id']))


@pytest.mark.parametrize('bad', ['eof', 'missing_usage', 'truncated', 'delta_after_stop', 'bad_usage'])
def test_protocol_failure_never_publishes(chat, bad):
    s = session(chat)
    value = frames()
    if bad == 'eof': value = value[:-1]
    if bad == 'missing_usage': value.pop(-2)
    if bad == 'truncated': value[1]['choices'][0]['finish_reason'] = 'length'
    if bad == 'delta_after_stop': value.insert(2, chunk({'content': 'bad'}))
    if bad == 'bad_usage': value[-2]['usage']['prompt_tokens'] = '30'
    calls, bodies = transport(chat, value)
    e = chat.begin(s['id'], {'content': 'test'}, 'key')
    events = asyncio.run(collect(chat, e['id']))
    assert events[-1]['type'] == 'error' and not any(e['type'] == 'done' for e in events)
    assert [m['role'] for m in chat.detail(s['id'])['messages']] == ['user']
    assert chat.ledger.snapshot(e['id'])['status'] == 'usage_unknown'
    asyncio.run(collect(chat, e['id']))
    assert len(calls) == 1 and bodies[0].closed == 1


def test_budget_rejects_before_send(chat):
    s = session(chat, token_budget=100)
    calls, _ = transport(chat, frames())
    e = chat.begin(s['id'], {'content': 'test'}, 'key')
    events = asyncio.run(collect(chat, e['id']))
    assert events[-1]['error_code'] == 'BUSINESS_TOKEN_BUDGET_EXHAUSTED'
    assert len(calls) == 0 and chat.ledger.snapshot(e['id'])['reserved'] == 0


def test_tool_loop_schema_permissions_and_usage(chat):
    seen = []
    async def lookup(args, agent, context):
        seen.append(args)
        return {'status': '可申请退款'}
    chat.tools.register('lookup', '查询合成订单', {'type': 'object', 'properties': {'order': {'type': 'string'}},
                                                 'required': ['order'], 'additionalProperties': False}, lookup)
    s = session(chat, tools=['lookup'])
    calls, _ = transport(chat, lambda n: frames(tool=True) if n == 1 else frames())
    e = chat.begin(s['id'], {'content': 'test'}, 'key')
    events = asyncio.run(collect(chat, e['id']))
    assert events[-1]['type'] == 'done' and len(calls) == 2 and seen == [{'order': '123'}]
    assert json.loads(calls[1].content)['messages'][-1]['role'] == 'tool'
    assert events[-1]['budget']['spent'] == 80
    assert any(e['type'] == 'tool' for e in events)


def test_undeclared_tool_denied(chat):
    s = session(chat)
    calls, _ = transport(chat, frames(tool=True))
    e = chat.begin(s['id'], {'content': 'test'}, 'key')
    events = asyncio.run(collect(chat, e['id']))
    assert events[-1]['error_code'] == 'SUPPORT_TOOL_DENIED' and len(calls) == 1


def test_busy_conflict_cancel_restart(chat):
    s = session(chat)
    e = chat.begin(s['id'], {'content': 'test'}, 'key')
    for body, key, code in [({'content': 'other'}, 'key', 'SUPPORT_IDEMPOTENCY_CONFLICT'),
                            ({'content': 'test'}, 'other', 'SUPPORT_SESSION_BUSY')]:
        with pytest.raises(Problem) as exc:
            chat.begin(s['id'], body, key)
        assert exc.value.code == code
    chat.recover()
    assert chat.get('exchanges', e['id'])['error_code'] == 'SUPPORT_RESTARTED'
    e2 = chat.begin(s['id'], {'content': 'retry'}, 'new')
    chat.cancel(e2['id'])
    assert asyncio.run(collect(chat, e2['id']))[-1]['error_code'] == 'SUPPORT_CANCELLED'


def test_disconnect_cancels_upstream_and_releases_session(chat):
    s = session(chat)
    closed = []
    async def hanging(providers, ident, payload):
        try:
            yield {'delta': 'preview'}
            await asyncio.Event().wait()
        finally:
            closed.append(True)
    chat.stream_model = hanging
    e = chat.begin(s['id'], {'content': 'test'}, 'key')
    async def scenario():
        stream = chat.stream(e['id'])
        assert (await anext(stream))['type'] == 'start'
        assert (await anext(stream))['type'] == 'delta'
        await stream.aclose()
    asyncio.run(scenario())
    assert closed == [True]
    assert chat.get('exchanges', e['id'])['status'] == 'cancelled'
    assert chat.active == {}
    chat.begin(s['id'], {'content': 'retry'}, 'new')


def test_http_chat_and_page(chat, tmp_path):
    with TestClient(create_app(tmp_path / 'http.db', run_worker=False), base_url='http://localhost') as client:
        providers = client.app.state.support_providers
        providers.transport = httpx.MockTransport(lambda r: httpx.Response(200, headers={'content-type': 'text/event-stream'}, stream=Stream(frames())))
        p = client.post('/api/local/support/providers', json={'name': 'mock', 'api_key': 'synthetic-secret', 'auto_probe': False}).json()
        a = client.post('/api/local/support/agents', json={'name': '客服', 'provider_id': p['id']})
        assert a.status_code == 201
        s = client.post('/api/local/support/sessions', json={'agent_id': a.json()['id']}).json()
        r = client.post('/api/local/support/sessions/'+s['id']+'/messages', json={'content': '退款'},
                        headers={'Idempotency-Key': 'one', 'Accept': 'text/event-stream'})
        assert r.status_code == 200 and 'event: done' in r.text and r.headers['cache-control'] == 'no-store'
        assert client.get('/support').status_code == 200
        assert '/harness/static/support.js' in client.get('/support', headers={'x-forwarded-prefix': '/harness'}).text


def test_cancel_waiting_tool_does_not_continue_or_publish(chat):
    started, closed = asyncio.Event(), []
    async def lookup(args, agent, context):
        started.set()
        try:
            await asyncio.Event().wait()
        finally:
            closed.append(True)
    chat.tools.register('lookup', 'lookup', {'type': 'object'}, lookup)
    s = session(chat, tools=['lookup'])
    calls, _ = transport(chat, frames(tool=True))
    e = chat.begin(s['id'], {'content': 'test'}, 'key')
    async def scenario():
        consumer = asyncio.create_task(collect(chat, e['id']))
        await asyncio.wait_for(started.wait(), 2)
        chat.cancel(e['id'])
        events = await asyncio.wait_for(consumer, 2)
        assert events[-1]['error_code'] == 'SUPPORT_CANCELLED'
    asyncio.run(scenario())
    assert closed == [True] and len(calls) == 1
    tool = json.loads(chat.store.db.execute('SELECT doc FROM support_tool_events').fetchone()[0])
    assert tool['status'] == 'cancelled' and 'output_sha256' not in tool


def test_success_terminal_cannot_be_cancelled(chat):
    s = session(chat)
    transport(chat, frames())
    e = chat.begin(s['id'], {'content': 'test'}, 'key')
    asyncio.run(collect(chat, e['id']))
    assert chat.cancel(e['id'])['status'] == 'succeeded'


def test_round_limit_stops_tool_loop(chat):
    async def lookup(args, agent, context):
        return {'ok': True}
    chat.tools.register('lookup', 'lookup', {'type': 'object'}, lookup)
    s = session(chat, tools=['lookup'], max_turns=2)
    calls, _ = transport(chat, frames(tool=True))
    e = chat.begin(s['id'], {'content': 'test'}, 'key')
    assert asyncio.run(collect(chat, e['id']))[-1]['error_code'] == 'SUPPORT_MAX_TURNS'
    assert len(calls) == 2
