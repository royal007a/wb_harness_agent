"""HA-0078: offline evidence, explicitly separated by SDK/HTTP/platform layers."""
import asyncio
import copy
import json
import os
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import threading

import httpx
import pytest
from fastapi.testclient import TestClient

from backend.app import create_app
from backend.analysis import Problem
from backend.dsh_provider import MODEL, BASE, parse_response


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv('HARNESS_DSH_LOCAL', 'enabled')
    monkeypatch.setenv('HARNESS_DSH_RUN_ROOT', str(tmp_path / 'owned'))
    monkeypatch.delenv('HARNESS_DSH_REAL_ENABLED', raising=False)
    monkeypatch.delenv('HARNESS_DSH_CREDENTIAL_REF', raising=False)
    from backend.agent_runtime import KeyringCredentialResolver
    monkeypatch.setattr(KeyringCredentialResolver, 'resolve',
                        lambda *a: pytest.fail('offline tests must never read credentials'))
    with TestClient(create_app(tmp_path / 'test.db', run_worker=False),
                    base_url='http://localhost') as value:
        yield value


MANY_CLAUSES = '\n'.join(f'第{i}条 条款{i}\n内容编号{i}。' for i in range(1, 21))


def body(**changes):
    return dict(objective='Read and cite evidence.', document='DOCUMENT_ALPHA: acceptance then payment.',
                mode='integration_probe', public_data_confirmed=True, **changes)


def submit(client, key='probe', **changes):
    payload = body()
    payload.update(changes)
    response = client.post('/api/local/dsh/runs', json=payload, headers={'Idempotency-Key': key})
    assert response.status_code == 201, response.text
    return response.json()['initial_run']['id']


def response(text='Answer clause-1', calls=None):
    message = {'content': text}
    if calls:
        message['tool_calls'] = [{'id': f'call_{i}', 'type': 'function', 'function': {
            'name': name, 'arguments': json.dumps(args)}} for i, (name, args) in enumerate(calls)]
    return {'choices': [{'finish_reason': 'tool_calls' if calls else 'stop', 'message': message}],
            'usage': {'prompt_tokens': 10, 'completion_tokens': 10, 'total_tokens': 20}}


def terminal(runtime, ident, status, reason):
    detail = runtime.detail(ident)
    assert detail['run']['status'] == status, detail
    assert detail['run']['exit_reason'] == reason, detail
    if status != 'succeeded':
        assert detail['artifacts'] == []
    events = runtime.store.events(ident)
    assert sum(e['event_type'] in {'run.succeeded', 'run.failed', 'run.cancelled'} for e in events) == 1
    return detail


# Actual official DSH SDK subprocess; only the Provider is synthetic.
@pytest.mark.parametrize('requested_calls', [8, 9])
def test_sdk_exact_model_call_cap(client, requested_calls):
    # HA-0079: distinct evidence each turn, so the cap (not the no-progress stop) is what is tested.
    ident = submit(client, document=MANY_CLAUSES)
    rt = client.app.state.service.dsh
    calls = []
    async def send(payload, limit):
        calls.append(payload)
        return parse_response(response(calls=[('read_clause', {'clause_id': f'clause-{len(calls)}'})]
                                       if len(calls) < requested_calls else None))
    rt.send_probe = send
    rt.execute(ident)
    detail = terminal(rt, ident, 'succeeded' if requested_calls == 8 else 'failed',
                      'COMPLETED' if requested_calls == 8 else 'DSH_MODEL_CALL_LIMIT')
    assert len(calls) == detail['budget']['calls'] == 8
    assert detail['budget']['spent'] == 160
    assert detail['budget']['reserved'] == 0
    assert not list(Path(os.environ['HARNESS_DSH_RUN_ROOT']).glob('run-*'))


@pytest.mark.parametrize('requested_tools', [16, 17])
def test_sdk_exact_tool_call_cap(client, requested_tools):
    ident = submit(client, document=MANY_CLAUSES)
    rt = client.app.state.service.dsh
    sent = 0
    async def send(payload, limit):
        nonlocal sent
        batch = min(4, requested_tools - sent)
        start, sent = sent, sent + batch
        return parse_response(response(calls=[('read_clause', {'clause_id': f'clause-{start + i + 1}'})
                                              for i in range(batch)]))
    rt.send_probe = send
    rt.execute(ident)
    detail = terminal(rt, ident, 'succeeded' if requested_tools == 16 else 'failed',
                      'COMPLETED' if requested_tools == 16 else 'DSH_TOOL_LIMIT')
    assert detail['budget']['calls'] == 5
    assert sum(e['event_type'] == 'dsh.tool.completed' for e in rt.store.events(ident)) == 16


@pytest.mark.parametrize('usage', [
    {'prompt_tokens': -1, 'completion_tokens': 1, 'total_tokens': 0},
    {'prompt_tokens': True, 'completion_tokens': 1, 'total_tokens': 2},
    {'prompt_tokens': 1.5, 'completion_tokens': 1, 'total_tokens': 2.5},
    {'prompt_tokens': 10, 'completion_tokens': 10, 'total_tokens': 99},
])
def test_sdk_invalid_usage_freezes_and_never_retries(client, usage):
    ident = submit(client)
    rt = client.app.state.service.dsh
    calls = []
    async def send(*args):
        calls.append(1)
        value = response(calls=[('read_clause', {'clause_id': 'clause-1'})])
        value['usage'] = usage
        return parse_response(value)
    rt.send_probe = send
    rt.execute(ident)
    detail = terminal(rt, ident, 'failed', 'BUSINESS_MODEL_USAGE_INVALID')
    assert calls == [1]
    assert detail['budget']['status'] == 'usage_unknown'
    assert detail['budget']['reserved'] > 0
    before = rt.store.db.total_changes
    rt.execute(ident)
    assert calls == [1] and rt.store.db.total_changes == before


def test_sdk_concurrent_execute_claims_once(client):
    ident = submit(client)
    rt = client.app.state.service.dsh
    entered, release = threading.Event(), threading.Event()
    original = rt.send_probe
    calls = []
    async def send(payload, limit):
        calls.append(1)
        entered.set()
        while not release.is_set():
            await asyncio.sleep(.01)
        return await original(payload, limit)
    rt.send_probe = send
    with ThreadPoolExecutor(max_workers=5) as pool:
        first = pool.submit(rt.execute, ident)
        try:
            assert entered.wait(15)
            duplicates = [pool.submit(rt.execute, ident) for _ in range(4)]
            for item in duplicates:
                item.result(timeout=3)
            assert len(calls) == 1
        finally:
            release.set()
        first.result(timeout=20)
    detail = terminal(rt, ident, 'succeeded', 'COMPLETED')
    assert len(calls) == 2 and len(detail['artifacts']) == 1


def test_sdk_search_then_read_has_real_tool_feedback(client):
    ident = submit(client, document='第1条 付款\n付款需验收。\n第2条 发票\n开具发票后结算。')
    rt = client.app.state.service.dsh
    calls = []
    async def send(payload, limit):
        calls.append(copy.deepcopy(payload))
        tools = [m for m in payload['messages'] if m['role'] == 'tool']
        if not tools:
            return parse_response(response(calls=[('search_document', {'query': '发票'})]))
        matches = json.loads(tools[0]['content'])['matches']
        assert matches and '发票' in matches[0]['text']
        ident = matches[0]['clause_id']
        if len(tools) == 1:
            return parse_response(response(calls=[('read_clause', {'clause_id': ident})]))
        return parse_response(response(text='证据 ' + ident))
    rt.send_probe = send
    rt.execute(ident)
    terminal(rt, ident, 'succeeded', 'COMPLETED')
    assert len(calls) == 3
    events = [e['data'] for e in rt.store.events(ident) if e['event_type'] == 'dsh.tool.completed']
    assert [e['tool'] for e in events] == ['search_document', 'read_clause']


def test_sdk_parallel_runs_do_not_share_document_or_workspace(client):
    rt = client.app.state.service.dsh
    ids = [submit(client, key=f'isolated-{i}', document=f'UNIQUE_DOC_{i}: synthetic payment.') for i in range(2)]
    with ThreadPoolExecutor(max_workers=2) as pool:
        list(pool.map(rt.execute, ids))
    for i, ident in enumerate(ids):
        detail = terminal(rt, ident, 'succeeded', 'COMPLETED')
        artifact = rt.store.db.execute('SELECT body FROM artifacts WHERE id=?', (detail['artifacts'][0]['id'],)).fetchone()[0]
        assert f'UNIQUE_DOC_{i}'.encode() in artifact
        assert f'UNIQUE_DOC_{1-i}'.encode() not in artifact
        assert 'UNIQUE_DOC_' not in json.dumps(rt.store.events(ident))
        assert detail['budget']['calls'] == 2
    assert not list(Path(os.environ['HARNESS_DSH_RUN_ROOT']).glob('run-*'))


# Platform orchestration only: substitute an Adapter to inject exact races/faults.
def drive_once(prompt, root, model, model_call, tool_call, emit, check):
    request = {'model': MODEL, 'purpose': 'primary', 'messages': [],
               'tools': [{'name': 'read_clause'}, {'name': 'search_document'}]}
    model_call(request)
    tool_call({'name': 'read_clause', 'arguments': {'clause_id': 'clause-1'}})
    return {'type': 'result', 'text': 'Answer clause-1', 'session_sha256': 'a' * 64,
            'turn_count': 1, 'runtime': 'deepseek-harness@0.2.1-alpha.1'}


def test_platform_cancel_after_adapter_result_before_publish(client):
    ident = submit(client)
    rt = client.app.state.service.dsh
    def late(*args):
        result = drive_once(*args)
        rt.cancel(ident)
        return result
    rt.adapter.run = late
    rt.execute(ident)
    terminal(rt, ident, 'cancelled', 'USER_CANCELLED')
    assert not any(e['event_type'] == 'artifact.created' for e in rt.store.events(ident))


def test_platform_publication_failure_rolls_back_artifact(client):
    ident = submit(client)
    rt = client.app.state.service.dsh
    rt.adapter.run = drive_once
    rt.store.db.execute("""CREATE TEMP TRIGGER reject_success BEFORE INSERT ON events
        WHEN NEW.doc LIKE '%run.succeeded%' BEGIN SELECT RAISE(ABORT, 'SYNTH_DB_SECRET'); END""")
    rt.execute(ident)
    terminal(rt, ident, 'failed', 'DSH_RUNTIME_FAILED')
    assert 'SYNTH_DB_SECRET' not in json.dumps(rt.store.events(ident))
    assert rt.store.db.execute('SELECT count(*) FROM artifacts WHERE run_id=?', (ident,)).fetchone()[0] == 0


@pytest.mark.parametrize('extra', [-1, 0])
def test_platform_second_call_reservation_exact_boundary(client, extra):
    from backend.dsh_provider import provider_payload
    from backend.store import dumps
    request = {'model': MODEL, 'purpose': 'primary', 'messages': [],
               'tools': [{'name': 'read_clause'}, {'name': 'search_document'}]}
    # HA-0081: the platform context assembler appends a state message; the second call
    # is sent after clause-1 was read, so its exact bound includes that state.
    from backend.dsh_context import assemble
    sent, _ = assemble(provider_payload(request), {'template': 'free', 'read': ['clause-1'],
                                                   'unread_exception_candidates': [], 'submission': None})
    bound = len(dumps(sent).encode()) + 4096 + 2048
    ident = submit(client, token_limit=bound + 20 + extra)
    rt = client.app.state.service.dsh
    sends = []
    async def send(*args):
        sends.append(1)
        return parse_response(response())
    def two_calls(prompt, root, model, model_call, tool_call, emit, check):
        result = drive_once(prompt, root, model, model_call, tool_call, emit, check)
        model_call(request)
        return result
    rt.send_probe, rt.adapter.run = send, two_calls
    rt.execute(ident)
    detail = terminal(rt, ident, 'failed' if extra < 0 else 'succeeded',
                      'BUSINESS_TOKEN_BUDGET_EXHAUSTED' if extra < 0 else 'COMPLETED')
    assert len(sends) == detail['budget']['calls'] == (1 if extra < 0 else 2)
    assert detail['budget']['spent'] == 20 * len(sends)
    assert detail['budget']['reserved'] == 0


@pytest.mark.parametrize('kind,mutation', [
    ('observation', {'text': 'SYNTH_EVENT_SECRET'}),
    ('observation', {'sha256': 'SYNTH_EVENT_SECRET'}),
    ('result', {'extra': 'SYNTH_EVENT_SECRET'}),
    ('result', {'runtime': 'fake-runtime'}),
])
def test_platform_rejects_untrusted_adapter_envelopes(client, kind, mutation):
    ident = submit(client)
    rt = client.app.state.service.dsh
    def probe(prompt, root, model, model_call, tool_call, emit, check):
        if kind == 'observation':
            emit({'type': 'observation', 'sha256': 'a'*64, 'bytes': 1, **mutation})
        result = drive_once(prompt, root, model, model_call, tool_call, emit, check)
        return {**result, **mutation}
    rt.adapter.run = probe
    rt.execute(ident)
    terminal(rt, ident, 'failed', 'DSH_VALIDATION_ERROR')
    assert 'SYNTH_EVENT_SECRET' not in json.dumps(rt.store.events(ident))


def test_platform_real_gate_rechecked_before_replay_and_execution(client, monkeypatch):
    monkeypatch.setenv('HARNESS_DSH_REAL_ENABLED', '1')
    monkeypatch.setenv('HARNESS_DSH_CREDENTIAL_REF', 'SYNTHETIC_REFERENCE')
    ident = submit(client, mode='real_provider')
    rt = client.app.state.service.dsh
    monkeypatch.delenv('HARNESS_DSH_REAL_ENABLED')
    before = rt.store.db.total_changes
    value = body()
    value['mode'] = 'real_provider'
    r = client.post('/api/local/dsh/runs', json=value, headers={'Idempotency-Key': 'probe'})
    assert r.status_code == 409 and r.json()['error']['code'] == 'DSH_PROVIDER_NOT_ADMITTED'
    assert before == rt.store.db.total_changes
    rt.adapter.run = lambda *a: pytest.fail('closed gate must not start SDK')
    rt.execute(ident)
    detail = terminal(rt, ident, 'failed', 'DSH_PROVIDER_NOT_ADMITTED')
    assert detail['budget'] is None


@pytest.mark.parametrize('key', ['', 'k' * 129])
def test_platform_invalid_key_does_not_write(client, key):
    store = client.app.state.service.store
    before = store.db.total_changes
    r = client.post('/api/local/dsh/runs', json=body(), headers={'Idempotency-Key': key})
    assert r.status_code == 422
    assert store.db.total_changes == before


def test_platform_maximum_key_is_accepted_and_replayed(client):
    key = 'k' * 128
    ident = submit(client, key=key)
    before = client.app.state.service.store.db.total_changes
    assert submit(client, key=key) == ident
    assert client.app.state.service.store.db.total_changes == before


@pytest.mark.parametrize('name,args,code', [
    ('bash', {'command': 'whoami'}, 'DSH_TOOL_POLICY'),
    ('read_clause', {'clause_id': '../../private'}, 'DSH_CLAUSE_NOT_FOUND'),
    ('read_clause', {'clause_id': 'clause-999'}, 'DSH_CLAUSE_NOT_FOUND'),
    ('read_clause', {'clause_id': 'clause-1', 'path': '/private'}, 'DSH_TOOL_INPUT'),
    ('search_document', {'query': ''}, 'DSH_TOOL_INPUT'),
    ('search_document', {'query': 'x' * 201}, 'DSH_TOOL_INPUT'),
    ('search_document', {'query': []}, 'DSH_TOOL_INPUT'),
])
def test_platform_tool_policy_cannot_be_bypassed(client, name, args, code):
    ident = submit(client)
    rt = client.app.state.service.dsh
    def probe(prompt, root, model, model_call, tool_call, emit, check):
        tool_call({'name': name, 'arguments': args})
        pytest.fail('invalid tool was accepted')
    rt.adapter.run = probe
    rt.execute(ident)
    terminal(rt, ident, 'failed', code)
    assert not any(e['event_type'] == 'dsh.tool.completed' for e in rt.store.events(ident))


def test_platform_concurrent_idempotency_and_queue_limit(client):
    rt = client.app.state.service.dsh
    barrier = threading.Barrier(4)
    def same(_):
        barrier.wait(timeout=5)
        return rt.create(body(), 'same-key')['initial_run']['id']
    with ThreadPoolExecutor(max_workers=4) as pool:
        ids = list(pool.map(same, range(4)))
    assert len(set(ids)) == 1 and len(rt.store.listing('runs')) == 1
    for i in range(6):
        rt.create(body(), f'queue-{i}')
    barrier = threading.Barrier(2)
    def last(i):
        barrier.wait(timeout=5)
        try:
            return rt.create(body(), f'last-{i}')['initial_run']['id']
        except Problem as exc:
            return exc.code
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(last, range(2)))
    assert results.count('RATE_LIMITED') == 1
    assert len(rt.store.listing('runs')) == len(rt.store.listing('tasks')) == 8
    before = rt.store.db.total_changes
    assert rt.create(body(), 'same-key')['initial_run']['id'] == ids[0]
    assert before == rt.store.db.total_changes


def test_platform_1001_events_and_empty_tail_are_read_only(client):
    ident = submit(client)
    rt = client.app.state.service.dsh
    with rt.store.transaction() as db:
        run = rt.store.get('runs', ident)
        for _ in range(1000):
            rt.store.event(db, run, 'dsh.observation', {'type': 'observation', 'sha256': 'a'*64, 'bytes': 1})
    before = rt.store.db.total_changes
    cursor, sequences, lengths = 0, [], []
    for _ in range(4):
        page = client.get(f'/api/local/dsh/runs/{ident}/events?after={cursor}').json()
        lengths.append(len(page['items']))
        sequences.extend(e['sequence'] for e in page['items'])
        cursor = page['next_cursor']
    assert lengths == [500, 500, 1, 0]
    assert sequences == list(range(1, 1002)) and cursor == 1001
    assert rt.store.db.total_changes == before


@pytest.mark.parametrize('field,limit', [('document', 20000), ('objective', 2000)])
def test_platform_request_character_limit_and_plus_one(client, field, limit):
    submit(client, **{field: '字' * limit})
    before = client.app.state.service.store.db.total_changes
    value = body()
    value[field] = '字' * (limit + 1)
    r = client.post('/api/local/dsh/runs', json=value, headers={'Idempotency-Key': 'over'})
    assert r.status_code == 422 and r.json()['error']['code'] == 'DSH_VALIDATION_ERROR'
    assert client.app.state.service.store.db.total_changes == before


# Provider wire contract only: HTTPX MockTransport; never external sockets.
class RawBody(httpx.AsyncByteStream):
    def __init__(self, data):
        self.data, self.reads, self.closed = data, 0, 0
    async def __aiter__(self):
        self.reads += 1
        yield self.data
    async def aclose(self):
        self.closed += 1


@pytest.mark.parametrize('status,encoding,oversize', [
    (200, None, False), (401, None, False), (429, None, False), (500, None, False),
    (307, None, False), (200, 'gzip', False), (200, 'identity', False), (200, '', False),
    (200, None, True),
])
def test_http_fixed_route_no_retry_no_decode_and_limits(monkeypatch, status, encoding, oversize):
    import backend.dsh_provider as provider
    value = json.dumps(response()).encode()
    stream = RawBody(b' ' * (256*1024 + 1) if oversize else value)
    calls, options = [], []
    def handler(request):
        calls.append(request)
        headers = {'content-encoding': encoding} if encoding is not None else {}
        headers['location'] = 'https://must-not-follow.invalid/'
        return httpx.Response(status, headers=headers, stream=stream)
    original = httpx.AsyncClient
    def make_client(**kwargs):
        options.append(kwargs)
        return original(**kwargs, transport=httpx.MockTransport(handler))
    monkeypatch.setattr(provider.httpx, 'AsyncClient', make_client)
    operation = provider.send_real({'model': MODEL, 'messages': [], 'stream': False}, 256000, 'SYNTHETIC_ONLY')
    if status == 200 and encoding is None and not oversize:
        assert asyncio.run(operation).value['text'] == 'Answer clause-1'
    else:
        with pytest.raises(Problem) as caught:
            asyncio.run(operation)
        assert caught.value.code == (f'DSH_PROVIDER_HTTP_{status}' if status != 200 else 'DSH_PROVIDER_INVALID')
    assert len(calls) == stream.closed == 1
    assert str(calls[0].url) == BASE + '/chat/completions'
    assert calls[0].headers['accept-encoding'] == 'identity'
    assert json.loads(calls[0].content)['max_tokens'] == 2048
    assert options == [{'timeout': 45, 'follow_redirects': False, 'trust_env': False}]
    if status != 200 or encoding is not None:
        assert stream.reads == 0


@pytest.mark.parametrize('variant', ['multi_choice', 'stop_with_calls', 'calls_without_calls',
    'duplicate_id', 'newline_id', 'five_calls', 'bad_arguments', 'array_arguments', 'huge_arguments', 'length'])
def test_provider_rejects_ambiguous_or_invalid_calls(variant):
    value = response(calls=[('read_clause', {'clause_id': 'clause-1'})])
    choice = value['choices'][0]
    call = choice['message']['tool_calls'][0]
    if variant == 'multi_choice': value['choices'].append(copy.deepcopy(choice))
    if variant == 'stop_with_calls': choice['finish_reason'] = 'stop'
    if variant == 'calls_without_calls': choice['message']['tool_calls'] = []
    if variant == 'duplicate_id': choice['message']['tool_calls'].append(copy.deepcopy(call))
    if variant == 'newline_id': call['id'] = 'id\n'
    if variant == 'five_calls': choice['message']['tool_calls'] *= 5
    if variant == 'bad_arguments': call['function']['arguments'] = '{'
    if variant == 'array_arguments': call['function']['arguments'] = '[]'
    if variant == 'huge_arguments': call['function']['arguments'] = json.dumps({'query': 'x'*1024})
    if variant == 'length': choice['finish_reason'] = 'length'
    with pytest.raises(Problem) as caught:
        parse_response(value)
    assert caught.value.code == 'DSH_PROVIDER_INVALID'


# Ownership recovery only, no SDK or DB.
@pytest.mark.parametrize('field,value', [('name', '../outside'), ('inode', -1), ('device', -1),
    ('pgid', True), ('pgid', 1), ('version', 2)])
def test_cleanup_rejects_corrupt_journal_without_touching_content(tmp_path, field, value):
    from adapters.dsh_workspace import OwnedWorkspace, cleanup_workspaces
    owned = OwnedWorkspace(tmp_path / 'root')
    marker = owned.path / 'marker'
    marker.write_text('SYNTHETIC_RETAIN')
    os.close(owned.lease)
    record = dict(owned.record)
    record[field] = value
    journal = owned.root / '.registry' / (owned.path.name + '.json')
    journal.write_text(json.dumps(record))
    assert cleanup_workspaces(owned.root, wait_seconds=0) == {'cleaned': 0, 'pending': 0, 'retained': 1}
    assert marker.read_text() == 'SYNTHETIC_RETAIN'


def test_cleanup_explicit_second_pass_after_lease_release(tmp_path):
    from adapters.dsh_workspace import OwnedWorkspace, cleanup_workspaces
    owned = OwnedWorkspace(tmp_path / 'root')
    assert cleanup_workspaces(owned.root, wait_seconds=0)['pending'] == 1
    assert owned.path.exists()
    os.close(owned.lease)
    assert cleanup_workspaces(owned.root, wait_seconds=0) == {'cleaned': 1, 'pending': 0, 'retained': 0}
    assert not owned.path.exists()
    assert cleanup_workspaces(owned.root, wait_seconds=0) == {'cleaned': 0, 'pending': 0, 'retained': 0}
