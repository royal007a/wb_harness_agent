"""Real Chromium + temporary HTTP/SQLite; no external Provider calls."""
import asyncio
import json
import socket
import threading
import time

import pytest
import uvicorn

pw = pytest.importorskip('playwright.sync_api', reason='explicit browser dependency required')
from backend.app import create_app


@pytest.fixture(scope='module')
def browser():
    with pw.sync_playwright() as driver:
        try:
            value = driver.chromium.launch()
        except pw.Error as exc:
            if "Executable doesn't exist" in str(exc):
                pytest.skip('Chromium executable is not installed')
            raise
        try:
            yield value
        finally:
            value.close()


@pytest.fixture
def ui(tmp_path, monkeypatch, browser):
    monkeypatch.delenv('HARNESS_AGENT_RUNTIME', raising=False)
    app = create_app(tmp_path / 'ui.db', run_worker=False)
    listener = socket.socket()
    listener.bind(('127.0.0.1', 0))
    port = listener.getsockname()[1]
    server = uvicorn.Server(uvicorn.Config(app, log_level='error', access_log=False))
    thread = threading.Thread(target=server.run, kwargs={'sockets': [listener]}, daemon=True)
    thread.start()
    try:
        deadline = time.monotonic() + 30
        while not server.started and thread.is_alive() and time.monotonic() < deadline:
            time.sleep(.01)
        assert server.started, 'isolated test server did not start'
        runtime = app.state.service.agent_runtime
        assert runtime.runtime_enabled() is False
        provider = runtime.create_provider({'name': 'UI test', 'type': 'openai_compatible', 'base_url': 'https://example.invalid'}, 'p')
        model = runtime.create_model({'provider_profile_id': provider['id'], 'display_name': 'UI model', 'model_id': 'synthetic', 'context_window': 4096}, 'm')
        agent = runtime.create_agent({'name': 'UI agent', 'description': '', 'system_prompt': 'test only', 'model_profile_id': model['id'], 'temperature': 0, 'max_output_tokens': 32, 'max_context_turns': 2}, 'a')
        page = browser.new_page(viewport={'width': 1440, 'height': 1000})
        errors = []
        page.on('pageerror', lambda error: errors.append(str(error)))
        try:
            yield page, runtime, agent, f'http://127.0.0.1:{port}'
            assert not errors
        finally:
            page.close()
    finally:
        server.should_exit = True
        thread.join(timeout=10)
        listener.close()
        assert not thread.is_alive(), 'test HTTP server leaked'


def session(runtime, agent, name, content=None):
    created = runtime.create_session({'agent_profile_id': agent['id'], 'title': name}, name)
    if content is not None:
        exchange = runtime.prepare_exchange(created['id'], {'content': content}, name + '-message')
        return created, exchange
    return created


def select(page, ident):
    page.locator(f'button[data-session="{ident}"]').click()


def test_failed_send_remains_visible_after_completion_reselection_and_reload(ui):
    page, runtime, agent, base = ui
    created = session(runtime, agent, 'failure case')
    page.goto(base + '/agent-runtime')
    select(page, created['id'])
    page.locator('#chat-input').fill('默认门禁应拒绝，不应消失。')
    page.locator('#send').click()
    pw.expect(page.locator('#send')).to_be_enabled()
    pw.expect(page.locator('#messages')).to_contain_text('MODEL_RUNTIME_DISABLED')
    pw.expect(page.locator('.bubble.assistant')).to_have_count(0)
    select(page, created['id'])
    pw.expect(page.locator('#messages')).to_contain_text('MODEL_RUNTIME_DISABLED')
    page.reload()
    select(page, created['id'])
    pw.expect(page.locator('#messages')).to_contain_text('MODEL_RUNTIME_DISABLED')
    pw.expect(page.locator('.exchange-status[data-status="failed"]')).to_have_count(1)
    detail = runtime.session_detail(created['id'])
    assert [m['role'] for m in detail['messages']] == ['user']
    assert detail['exchanges'][0]['model_calls'] == 0
    page.set_viewport_size({'width': 390, 'height': 844})
    assert page.evaluate('document.documentElement.scrollWidth <= window.innerWidth')


@pytest.mark.parametrize('status,label', [('queued', '排队中'), ('streaming', '生成中'), ('cancelled', '已取消')])
def test_non_answer_exchange_states_are_displayed_separately(ui, status, label):
    page, runtime, agent, base = ui
    created, exchange = session(runtime, agent, status, '用户问题')
    if status == 'cancelled':
        runtime.cancel_exchange(exchange['id'])
    elif status == 'streaming':
        runtime._claim(exchange['id'])
    page.goto(base + '/agent-runtime')
    select(page, created['id'])
    pw.expect(page.locator('#messages')).to_contain_text(label)
    pw.expect(page.locator('.exchange-status')).to_contain_text(exchange['id'])
    pw.expect(page.locator('.bubble.assistant')).to_have_count(0)


def test_successful_message_is_not_duplicated_by_exchange_card(ui):
    page, runtime, agent, base = ui
    created, exchange = session(runtime, agent, 'success', 'synthetic input')

    class SyntheticAdapter:
        def require(self, _):
            return self

        async def stream(self, _):
            yield '合成验证输出，不是真实模型。'

    class SyntheticCredential:
        def resolve(self, _):
            return 'synthetic'

    runtime.adapters, runtime.credentials = SyntheticAdapter(), SyntheticCredential()
    runtime._runtime_enabled = True

    # Exercise the HTTP stream in the server's loop. Playwright's synchronous
    # API already owns the test thread's event loop; do not nest asyncio.run.
    try:
        response = page.request.post(base + '/api/local/agent-runtime/sessions/' + created['id'] + '/messages',
            data={'content': 'synthetic input'}, headers={'Accept': 'text/event-stream', 'Idempotency-Key': 'success-message'})
        assert response.status == 200
        events = [json.loads(line[5:].strip()) for line in response.text().splitlines() if line.startswith('data:')]
        assert events[-1]['type'] == 'done'
    finally:
        runtime._runtime_enabled = False
    page.goto(base + '/agent-runtime')
    select(page, created['id'])
    pw.expect(page.locator('.bubble.assistant')).to_have_count(1)
    pw.expect(page.locator('.bubble.assistant')).to_have_text('ASSISTANT合成验证输出，不是真实模型。')
    pw.expect(page.locator('.exchange-status')).to_contain_text('已完成')
    pw.expect(page.locator('.exchange-status')).not_to_contain_text('合成验证输出')


def test_exchange_and_user_text_do_not_inject_html(ui):
    page, runtime, agent, base = ui
    injected = '<img src=x onerror="window.uiInjected=1">'
    created, exchange = session(runtime, agent, 'escaping', injected)
    runtime._failure(exchange['id'], injected)
    page.goto(base + '/agent-runtime')
    select(page, created['id'])
    pw.expect(page.locator('.exchange-status')).to_contain_text(injected)
    pw.expect(page.locator('.bubble.user')).to_contain_text(injected)
    pw.expect(page.locator('#messages img')).to_have_count(0)
    assert page.evaluate('window.uiInjected === undefined')


def test_slow_old_session_detail_cannot_replace_new_selection(ui):
    page, runtime, agent, base = ui
    first, exchange = session(runtime, agent, 'first', 'first message')
    runtime.cancel_exchange(exchange['id'])
    second, exchange2 = session(runtime, agent, 'second', 'second message')
    runtime.cancel_exchange(exchange2['id'])
    held = []
    page.route('**/sessions/' + first['id'], lambda route: held.append(route))
    page.goto(base + '/agent-runtime')
    select(page, first['id'])
    pw.expect(page.locator(f'button[data-session="{second["id"]}"]')).to_be_visible()
    assert held, 'first request was not dispatched'
    select(page, second['id'])
    pw.expect(page.locator('#messages')).to_contain_text('second message')
    held[0].fulfill(json=runtime.session_detail(first['id']))
    # Evaluate after the first selection promise has resumed, not before delivery.
    page.wait_for_function('state.pendingSelectionCount === 0')
    pw.expect(page.locator('#messages')).to_contain_text('second message')
    pw.expect(page.locator('#messages')).not_to_contain_text('first message')
    pw.expect(page.locator(f'button[data-session="{second["id"]}"]')).to_have_class('selected')


def test_stream_completion_does_not_refetch_or_replace_other_session(ui):
    page, runtime, agent, base = ui
    first = session(runtime, agent, 'stream origin')
    second, exchange = session(runtime, agent, 'read destination', 'destination message')
    runtime.cancel_exchange(exchange['id'])
    held, reads = [], []
    page.route('**/sessions/' + first['id'] + '/messages', lambda route: held.append(route))
    page.on('request', lambda request: reads.append(request.url) if request.url.endswith('/sessions/' + second['id']) else None)
    page.goto(base + '/agent-runtime')
    select(page, first['id'])
    page.locator('#chat-input').fill('原会话消息')
    page.locator('#send').click()
    assert held
    select(page, second['id'])
    pw.expect(page.locator('#messages')).to_contain_text('destination message')
    held[0].fulfill(status=200, content_type='text/event-stream', body='data: ' + json.dumps({'type': 'error', 'error_code': 'MODEL_RUNTIME_DISABLED'}) + '\n\n')
    pw.expect(page.locator('#send')).to_be_enabled()
    pw.expect(page.locator('#messages')).to_contain_text('destination message')
    assert len(reads) == 1, 'old stream refreshed the newly selected session'


def test_exchange_without_visible_user_message_is_not_lost(ui):
    page, runtime, agent, base = ui
    created, exchange = session(runtime, agent, 'orphan history', 'missing from view')
    runtime._failure(exchange['id'], 'MODEL_RUNTIME_DISABLED')
    detail = runtime.session_detail(created['id'])
    detail['messages'] = []
    page.route('**/sessions/' + created['id'], lambda route: route.fulfill(json=detail))
    page.goto(base + '/agent-runtime')
    select(page, created['id'])
    pw.expect(page.locator('.exchange-status')).to_contain_text(exchange['id'])
    pw.expect(page.locator('.exchange-status')).to_contain_text('MODEL_RUNTIME_DISABLED')
    pw.expect(page.locator('.bubble.assistant')).to_have_count(0)


def test_early_stream_eof_never_commits_preview_as_answer(ui):
    page, runtime, agent, base = ui
    created = session(runtime, agent, 'truncated transport')
    page.route('**/sessions/' + created['id'] + '/messages', lambda route: route.fulfill(
        status=200, content_type='text/event-stream',
        body='data: ' + json.dumps({'type': 'delta', 'content': 'uncommitted'}) + '\n\n'))
    page.goto(base + '/agent-runtime')
    select(page, created['id'])
    page.locator('#chat-input').fill('truncated')
    page.locator('#send').click()
    pw.expect(page.locator('#send')).to_be_enabled()
    pw.expect(page.locator('.transient')).to_contain_text('连接提前结束')
    pw.expect(page.locator('.bubble.assistant')).to_have_count(0)
    assert runtime.session_detail(created['id'])['messages'] == []


def test_stop_display_does_not_claim_server_cancelled(ui):
    page, runtime, agent, base = ui
    created = session(runtime, agent, 'abort transport')
    held = []
    page.route('**/sessions/' + created['id'] + '/messages', lambda route: held.append(route))
    page.goto(base + '/agent-runtime')
    select(page, created['id'])
    page.locator('#chat-input').fill('abort before response')
    page.locator('#send').click()
    pw.expect(page.locator('#stop')).to_be_visible()
    page.locator('#stop').click()
    pw.expect(page.locator('#send')).to_be_enabled()
    pw.expect(page.locator('.transient')).to_contain_text('不代表服务端已确认取消')
    pw.expect(page.locator('.exchange-status[data-status="cancelled"]')).to_have_count(0)
    pw.expect(page.locator('.bubble.assistant')).to_have_count(0)


def test_live_synthetic_stream_is_only_preview_until_persisted(ui):
    page, runtime, agent, base = ui
    created = session(runtime, agent, 'live synthetic stream')
    release = threading.Event()

    class SyntheticAdapter:
        def require(self, _):
            return self

        async def stream(self, _):
            yield '合成中间内容'
            while not release.is_set():
                await asyncio.sleep(.01)
            yield '，已经结束。'

    class SyntheticCredential:
        def resolve(self, _):
            return 'synthetic'

    runtime.adapters, runtime.credentials = SyntheticAdapter(), SyntheticCredential()
    runtime._runtime_enabled = True
    try:
        page.goto(base + '/agent-runtime')
        select(page, created['id'])
        page.locator('#chat-input').fill('本机合成 HTTP 流，无外部模型')
        page.locator('#send').click()
        pw.expect(page.locator('.transient')).to_contain_text('流中预览（未持久化）')
        pw.expect(page.locator('.transient')).to_contain_text('合成中间内容')
        pw.expect(page.locator('.bubble.assistant')).to_have_count(0)
        assert [m['role'] for m in runtime.session_detail(created['id'])['messages']] == ['user']
        release.set()
        pw.expect(page.locator('#send')).to_be_enabled()
        pw.expect(page.locator('.transient')).to_have_count(0)
        pw.expect(page.locator('.bubble.assistant')).to_have_count(1)
        pw.expect(page.locator('.bubble.assistant')).to_contain_text('合成中间内容，已经结束。')
        pw.expect(page.locator('.exchange-status[data-status="succeeded"]')).to_have_count(1)
    finally:
        release.set()
        runtime._runtime_enabled = False
