"""HTTP transport for the trusted local-user workbench."""
import asyncio
import fcntl
import json
import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles

from .analysis import MAX_BYTES, Problem
from .service import BUNDLE, CONTROL, ROOT, Service, local_task
from .store import Store, uid
from .readiness import readiness


def create_app(db_path=None, run_worker=True):
    @asynccontextmanager
    async def lifespan(app):
        target = Path(db_path or os.environ.get('HARNESS_DB', ROOT / '.local/harness.db'))
        target.parent.mkdir(parents=True, exist_ok=True)
        lease = target.with_suffix('.lock').open('a')
        try:
            fcntl.flock(lease, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            lease.close()
            raise RuntimeError('A Harness process already owns this database') from None
        store = Store(target)
        service = Service(store)
        app.state.service = service
        if run_worker:
            service.start()
        try:
            yield
        finally:
            service.stop()
            store.close()
            lease.close()

    app = FastAPI(title='HarnessAgent Local API', version='0.1.0', lifespan=lifespan, docs_url=None, redoc_url=None)

    def error(code, message, status, request_id=None):
        return JSONResponse({'error': {'code': code, 'message': message, 'retryable': False,
                                       'request_id': request_id or uid('req')}}, status_code=status)

    @app.middleware('http')
    async def local_boundary(request, call_next):
        request_id = uid('req')
        host = request.headers.get('host', '')
        if host.split(':')[0] not in {'localhost', '127.0.0.1'}:
            return error('FORBIDDEN', '仅支持本地访问。', 403, request_id)
        origin = request.headers.get('origin')
        if origin and origin != 'http://' + host:
            return error('FORBIDDEN', '不允许跨站访问本地工作台。', 403, request_id)
        oauth_callback = request.method == 'GET' and request.url.path == '/api/local/connectors/baidu-netdisk/callback'
        if request.headers.get('sec-fetch-site') == 'cross-site' and not oauth_callback:
            return error('FORBIDDEN', '不允许跨站访问。', 403, request_id)
        try:
            response = await call_next(request)
        except Exception:
            return error('INTERNAL_ERROR', '请求失败，请查看运行事件。', 500, request_id)
        response.headers.update({'X-Request-ID': request_id, 'X-Content-Type-Options': 'nosniff',
                                 'Referrer-Policy': 'no-referrer', 'Cache-Control': 'no-store',
                                 'Content-Security-Policy': "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' blob:; object-src 'none'; frame-ancestors 'none'; base-uri 'none'"})
        return response

    @app.exception_handler(Problem)
    async def problem_handler(request, exc):
        return error(exc.code, exc.message, exc.status)

    @app.exception_handler(RequestValidationError)
    async def validation_handler(request, exc):
        return error('VALIDATION_ERROR', '路径或查询参数无效。', 422)

    async def read_body(request, limit=MAX_BYTES):
        chunks = bytearray()
        try:
            async with asyncio.timeout(10):
                async for part in request.stream():
                    chunks.extend(part)
                    if len(chunks) > limit:
                        raise Problem('PAYLOAD_TOO_LARGE', '请求超过大小限制。', 413)
        except TimeoutError:
            raise Problem('TIMEOUT', '上传超时。', 408) from None
        return bytes(chunks)

    async def json_body(request):
        if request.headers.get('content-type', '').split(';')[0] != 'application/json':
            raise Problem('VALIDATION_ERROR', '请求必须为 application/json。', 415)
        try:
            def invalid_constant(value):
                raise ValueError('Non-finite JSON constant')
            body = json.loads(await read_body(request, 32768), parse_constant=invalid_constant)
            json.dumps(body, allow_nan=False)
        except (ValueError, UnicodeDecodeError):
            raise Problem('VALIDATION_ERROR', 'JSON 无效。', 422) from None
        if not isinstance(body, dict):
            raise Problem('VALIDATION_ERROR', '请求必须为 JSON 对象。', 422)
        return body

    @app.get('/api/v1/health')
    def health():
        return {'status': 'ok', 'version': '0.1.0', 'mode': 'local_single_user', 'model_calls_enabled': False}

    @app.get('/api/v1/engines')
    def engines():
        return {'items': [
            {'id': 'engine_mock_analytics', 'name': 'Local Analytics', 'status': 'available', 'description': '固定统计 · 真实计算 · 无模型调用'},
            {'id': 'engine_local_research_demo', 'name': 'Research Orchestration', 'status': 'available', 'description': '离线编排演示 · 最多 9 个 Child Run / 3 并发 · 非 Claude 运行'},
            {'id': 'engine_research_multi_agent_simulation', 'name': 'Research Agent Simulation', 'status': 'available', 'description': '三角色 Agent / Skill / Tool 契约模拟 · 零模型零网络 · 非 Claude 运行'},
            {'id': 'engine_claude_research_native', 'name': 'Native Claude Research', 'status': 'blocked', 'description': '原生 SubAgent / Skills / MCP 已受控实现 · 需模型、数据源、预算与 L3 探针授权'},
            {'id': 'engine_smolagents_code', 'name': 'Smolagents', 'status': 'blocked', 'description': 'CodeAct · 真实模型尚未接入 · SDK/VM 探针状态见 /api/v1/readiness'},
            {'id': 'engine_claude', 'name': 'Claude Agent SDK', 'status': 'planned', 'description': '研报与复杂编排 · P1'},
            {'id': 'engine_deepagents', 'name': 'Deep Agents', 'status': 'planned', 'description': '动态知识与记忆 · P2'},
            {'id': 'engine_pi', 'name': 'Pi', 'status': 'planned', 'description': 'TypeScript 审查 · P2'}]}

    @app.get('/api/v1/readiness')
    def engine_readiness():
        return readiness()

    @app.get('/api/v1/resources')
    def resources():
        return {'items': app.state.service.store.listing('resources')}

    @app.get('/api/local/external-skills/runtime')
    def external_skill_runtime():
        return app.state.service.external_skills.runtime_status()

    @app.get('/api/local/external-skills/packages')
    def external_skill_packages():
        return app.state.service.external_skills.packages()

    @app.post('/api/local/external-skills/packages', status_code=201)
    async def external_skill_package_register(request: Request, source_label: str):
        content_type = request.headers.get('content-type', '').split(';', 1)[0].strip().lower()
        if content_type != 'application/zip':
            raise Problem('VALIDATION_ERROR', '外部 Skill 包必须使用 application/zip 上传。', 415)
        return app.state.service.external_skills.register_package(
            await read_body(request, 128 * 1024), {'source_label': source_label}, request.headers.get('idempotency-key')
        )

    @app.post('/api/local/external-skills/packages/{package_id}:execute')
    async def external_skill_execute(package_id: str, request: Request):
        return app.state.service.external_skills.execute(
            package_id, await json_body(request), request.headers.get('idempotency-key')
        )

    @app.get('/api/local/memory/runtime')
    def memory_runtime():
        return app.state.service.memory.runtime_status()

    @app.get('/api/local/memory/banks')
    def memory_banks():
        return app.state.service.memory.banks()

    @app.post('/api/local/memory/banks', status_code=201)
    async def memory_bank_create(request: Request):
        return app.state.service.memory.create_bank(await json_body(request), request.headers.get('idempotency-key'))

    @app.get('/api/local/memory/banks/{bank_id}')
    def memory_bank_detail(bank_id: str):
        return app.state.service.memory.bank_detail(bank_id)

    @app.post('/api/local/memory/banks/{bank_id}/retain', status_code=201)
    async def memory_retain(bank_id: str, request: Request):
        return app.state.service.memory.retain(bank_id, await json_body(request), request.headers.get('idempotency-key'))

    @app.post('/api/local/memory/banks/{bank_id}/entities', status_code=201)
    async def memory_entity_create(bank_id: str, request: Request):
        return app.state.service.memory.create_entity(bank_id, await json_body(request), request.headers.get('idempotency-key'))

    @app.post('/api/local/memory/banks/{bank_id}/relations', status_code=201)
    async def memory_relation_create(bank_id: str, request: Request):
        return app.state.service.memory.create_relation(bank_id, await json_body(request), request.headers.get('idempotency-key'))

    @app.post('/api/local/memory/banks/{bank_id}:recall')
    async def memory_recall(bank_id: str, request: Request):
        return app.state.service.memory.recall(bank_id, await json_body(request))

    @app.post('/api/local/memory/banks/{bank_id}:context')
    async def memory_context(bank_id: str, request: Request):
        return app.state.service.memory.context(bank_id, await json_body(request))

    @app.post('/api/local/memory/banks/{bank_id}:recall-details')
    async def memory_recall_details(bank_id: str, request: Request):
        return app.state.service.memory.recall_details(bank_id, await json_body(request))

    @app.post('/api/local/memory/banks/{bank_id}:graph-recall')
    async def memory_graph_recall(bank_id: str, request: Request):
        return app.state.service.memory.graph_recall(bank_id, await json_body(request))

    @app.post('/api/local/memory/banks/{bank_id}:resolve-entity')
    async def memory_entity_resolve(bank_id: str, request: Request):
        return app.state.service.memory.resolve_entity(bank_id, await json_body(request))

    @app.post('/api/local/memory/banks/{bank_id}:fact-lineage')
    async def memory_fact_lineage(bank_id: str, request: Request):
        return app.state.service.memory.fact_lineage(bank_id, await json_body(request))

    @app.post('/api/local/memory/sources/{source_id}:retract')
    async def memory_source_retract(source_id: str, request: Request):
        if await json_body(request) != {}:
            raise Problem('VALIDATION_ERROR', '撤回请求必须为空 JSON 对象。', 422)
        return app.state.service.memory.retract_source(source_id, request.headers.get('idempotency-key'))

    @app.delete('/api/local/memory/sources/{source_id}')
    async def memory_source_delete(source_id: str, request: Request):
        if request.headers.get('content-length') not in (None, '0'):
            raise Problem('VALIDATION_ERROR', '删除请求不接受请求体。', 422)
        return app.state.service.memory.delete_source(source_id, request.headers.get('idempotency-key'))

    @app.get('/api/local/team/runtime')
    def team_runtime():
        return app.state.service.team.runtime_status()

    @app.get('/api/local/team/tasks')
    def team_tasks():
        return app.state.service.team.tasks()

    @app.post('/api/local/team/tasks', status_code=201)
    async def team_task_create(request: Request):
        return app.state.service.team.create_task(await json_body(request), request.headers.get('idempotency-key'))

    @app.get('/api/local/team/tasks/{task_id}')
    def team_task_detail(task_id: str):
        return app.state.service.team.detail(task_id)

    @app.post('/api/local/team/tasks/{task_id}:claim')
    async def team_task_claim(task_id: str, request: Request):
        return app.state.service.team.claim(task_id, await json_body(request), request.headers.get('idempotency-key'))

    @app.post('/api/local/team/tasks/{task_id}/handoffs', status_code=201)
    async def team_task_handoff(task_id: str, request: Request):
        return app.state.service.team.create_handoff(task_id, await json_body(request), request.headers.get('idempotency-key'))

    @app.post('/api/local/team/tasks/{task_id}:submit')
    async def team_task_submit(task_id: str, request: Request):
        return app.state.service.team.submit(task_id, await json_body(request), request.headers.get('idempotency-key'))

    @app.post('/api/local/team/tasks/{task_id}:close')
    async def team_task_close(task_id: str, request: Request):
        return app.state.service.team.close(task_id, await json_body(request), request.headers.get('idempotency-key'))

    @app.post('/api/local/team/tasks/{task_id}/gate-decisions', status_code=201)
    async def team_task_gate_decision(task_id: str, request: Request):
        return app.state.service.team.gate_decision(task_id, await json_body(request), request.headers.get('idempotency-key'))

    @app.get('/api/local/agent-lab/runtime')
    def agent_lab_runtime():
        return app.state.service.agent_lab.runtime_status()

    @app.get('/api/local/agent-runtime/runtime')
    def agent_runtime_status():
        return app.state.service.agent_runtime.runtime_status()

    @app.get('/api/local/agent-runtime/providers')
    def agent_runtime_providers():
        return app.state.service.agent_runtime.providers()

    @app.post('/api/local/agent-runtime/providers', status_code=201)
    async def agent_runtime_provider_create(request: Request):
        return app.state.service.agent_runtime.create_provider(await json_body(request), request.headers.get('idempotency-key'))

    @app.get('/api/local/agent-runtime/providers/{provider_id}/readiness')
    def agent_runtime_provider_readiness(provider_id: str):
        return app.state.service.agent_runtime.provider_readiness(provider_id)

    @app.get('/api/local/agent-runtime/models')
    def agent_runtime_models():
        return app.state.service.agent_runtime.models()

    @app.post('/api/local/agent-runtime/models', status_code=201)
    async def agent_runtime_model_create(request: Request):
        return app.state.service.agent_runtime.create_model(await json_body(request), request.headers.get('idempotency-key'))

    @app.get('/api/local/agent-runtime/agents')
    def agent_runtime_agents():
        return app.state.service.agent_runtime.agents()

    @app.post('/api/local/agent-runtime/agents', status_code=201)
    async def agent_runtime_agent_create(request: Request):
        return app.state.service.agent_runtime.create_agent(await json_body(request), request.headers.get('idempotency-key'))

    @app.get('/api/local/agent-runtime/sessions')
    def agent_runtime_sessions():
        return app.state.service.agent_runtime.sessions()

    @app.post('/api/local/agent-runtime/sessions', status_code=201)
    async def agent_runtime_session_create(request: Request):
        return app.state.service.agent_runtime.create_session(await json_body(request), request.headers.get('idempotency-key'))

    @app.get('/api/local/agent-runtime/sessions/{session_id}')
    def agent_runtime_session_detail(session_id: str):
        return app.state.service.agent_runtime.session_detail(session_id)

    @app.post('/api/local/agent-runtime/sessions/{session_id}/messages')
    async def agent_runtime_message_create(session_id: str, request: Request):
        if 'text/event-stream' not in request.headers.get('accept', ''):
            raise Problem('VALIDATION_ERROR', '消息接口要求 Accept: text/event-stream。', 406)
        exchange = app.state.service.agent_runtime.prepare_exchange(
            session_id, await json_body(request), request.headers.get('idempotency-key')
        )

        async def stream():
            disconnected = False
            try:
                async for payload in app.state.service.agent_runtime.stream_exchange(exchange['id']):
                    if await request.is_disconnected():
                        disconnected = True
                        return
                    yield 'data: ' + json.dumps(payload, ensure_ascii=False) + '\n\n'
            except asyncio.CancelledError:
                disconnected = True
                raise
            finally:
                if disconnected:
                    app.state.service.agent_runtime.cancel_exchange(exchange['id'])

        return StreamingResponse(stream(), media_type='text/event-stream', headers={
            'X-Accel-Buffering': 'no', 'Cache-Control': 'no-store', 'Connection': 'keep-alive',
        })

    @app.get('/api/local/agent-lab/providers')
    def agent_lab_providers():
        return app.state.service.agent_lab.providers()

    @app.post('/api/local/agent-lab/providers', status_code=201)
    async def agent_lab_provider_create(request: Request):
        return app.state.service.agent_lab.create_provider(await json_body(request), request.headers.get('idempotency-key'))

    @app.get('/api/local/agent-lab/models')
    def agent_lab_models():
        return app.state.service.agent_lab.models()

    @app.post('/api/local/agent-lab/models', status_code=201)
    async def agent_lab_model_create(request: Request):
        return app.state.service.agent_lab.create_model(await json_body(request), request.headers.get('idempotency-key'))

    @app.get('/api/local/agent-lab/agents')
    def agent_lab_agents():
        return app.state.service.agent_lab.agents()

    @app.post('/api/local/agent-lab/agents', status_code=201)
    async def agent_lab_agent_create(request: Request):
        return app.state.service.agent_lab.create_agent(await json_body(request), request.headers.get('idempotency-key'))

    @app.get('/api/local/agent-lab/sessions')
    def agent_lab_sessions():
        return app.state.service.agent_lab.sessions()

    @app.post('/api/local/agent-lab/sessions', status_code=201)
    async def agent_lab_session_create(request: Request):
        return app.state.service.agent_lab.create_session(await json_body(request), request.headers.get('idempotency-key'))

    @app.get('/api/local/agent-lab/sessions/{session_id}')
    def agent_lab_session_detail(session_id: str):
        return app.state.service.agent_lab.session_detail(session_id)

    @app.post('/api/local/agent-lab/sessions/{session_id}/messages')
    async def agent_lab_message_create(session_id: str, request: Request):
        if 'text/event-stream' not in request.headers.get('accept', ''):
            raise Problem('VALIDATION_ERROR', '消息接口要求 Accept: text/event-stream。', 406)
        exchange = app.state.service.agent_lab.send_message(
            session_id, await json_body(request), request.headers.get('idempotency-key')
        )

        async def stream():
            try:
                for chunk in app.state.service.agent_lab.stream_chunks(exchange):
                    if await request.is_disconnected():
                        return
                    payload = {'type': 'delta', 'content': chunk, 'message_id': exchange['assistant_message_id'],
                               'model_calls': 0, 'provider_calls': 0}
                    yield 'data: ' + json.dumps(payload, ensure_ascii=False) + '\n\n'
                    await asyncio.sleep(0.03)
                if not await request.is_disconnected():
                    payload = {'type': 'done', 'message_id': exchange['assistant_message_id'], 'finish_reason': 'stop',
                               'model_calls': 0, 'provider_calls': 0}
                    yield 'data: ' + json.dumps(payload, ensure_ascii=False) + '\n\n'
            except asyncio.CancelledError:
                raise
            except Exception:
                payload = {'type': 'error', 'error_code': 'LOCAL_DEMO_STREAM_FAILED',
                           'model_calls': 0, 'provider_calls': 0}
                yield 'data: ' + json.dumps(payload, ensure_ascii=False) + '\n\n'

        return StreamingResponse(stream(), media_type='text/event-stream', headers={
            'X-Accel-Buffering': 'no', 'Cache-Control': 'no-store', 'Connection': 'keep-alive',
        })

    @app.get('/api/local/connectors/baidu-netdisk')
    def baidu_netdisk_status():
        return app.state.service.baidu_netdisk.status()

    @app.post('/api/local/connectors/baidu-netdisk/authorization', status_code=201)
    async def baidu_netdisk_authorization(request: Request):
        body = await json_body(request)
        if body:
            raise Problem('VALIDATION_ERROR', '发起授权不接受请求字段。', 422)
        with app.state.service.store.transaction() as db:
            return app.state.service.baidu_netdisk.authorization(db, request.headers.get('idempotency-key'))

    @app.get('/api/local/connectors/baidu-netdisk/callback', include_in_schema=False)
    def baidu_netdisk_callback(code: str | None = None, state: str | None = None, error: str | None = None):
        result = app.state.service.baidu_netdisk.callback(code=code, state=state, error=error)
        title = '授权已完成' if result['connected'] else '授权未完成'
        return HTMLResponse('<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><title>' + title +
                            '</title></head><body><h1>' + title + '</h1><p>' + result['message'] +
                            '</p><p>你可以关闭本页并返回 HarnessAgent。</p></body></html>')

    @app.post('/api/local/connectors/baidu-netdisk:disconnect')
    async def baidu_netdisk_disconnect(request: Request):
        body = await json_body(request)
        if body:
            raise Problem('VALIDATION_ERROR', '断开授权不接受请求字段。', 422)
        key = request.headers.get('idempotency-key')
        if not key or len(key) > 128:
            raise Problem('VALIDATION_ERROR', '必须提供 1–128 字符的 Idempotency-Key。', 422)
        # Deleting a token is naturally idempotent.  Do not mix the external
        # Keychain side effect with a SQLite transaction merely to retain a
        # replay record: a database commit failure must not make the outcome
        # ambiguous after a successful credential deletion.
        return app.state.service.baidu_netdisk.disconnect()

    @app.post('/api/local/research', status_code=202)
    async def research_create(request: Request):
        return app.state.service.research.create(await json_body(request), request.headers.get('idempotency-key'))

    @app.get('/api/local/research')
    def research_list():
        store = app.state.service.store
        return {'items': [r for r in store.listing('runs')
                          if r['selected_engine'] == 'engine_local_research_demo' and not r.get('parent_run_id')]}

    @app.get('/api/local/research/{run_id}')
    def research_detail(run_id: str):
        return app.state.service.research.detail(run_id)

    @app.get('/research', include_in_schema=False)
    def research_page():
        return FileResponse(ROOT / 'frontend/research.html')

    @app.post('/api/local/research-agents', status_code=202)
    async def research_agents_create(request: Request):
        return app.state.service.research_agents.create(await json_body(request), request.headers.get('idempotency-key'))

    @app.get('/api/local/research-agents')
    def research_agents_list():
        store = app.state.service.store
        return {'items': [run for run in store.listing('runs')
                          if run['selected_engine'] == 'engine_research_multi_agent_simulation' and not run.get('parent_run_id')]}

    @app.get('/api/local/research-agents/{run_id}')
    def research_agents_detail(run_id: str):
        return app.state.service.research_agents.detail(run_id)

    @app.get('/api/local/research-native/runtime')
    def research_native_runtime():
        from adapters.claude_research import runtime_status
        return runtime_status()

    @app.post('/api/local/research-native/documents', status_code=201)
    async def research_native_document(request: Request, name: str):
        if request.headers.get('content-type', '').split(';')[0] != 'application/pdf':
            raise Problem('VALIDATION_ERROR', '原生投研资料上传要求 application/pdf。', 415)
        return app.state.service.research_pdf_resource(name, await read_body(request, 15 * 1024 * 1024))

    @app.post('/api/local/research-native', status_code=202)
    async def research_native_create(request: Request):
        return app.state.service.research_native.create(await json_body(request), request.headers.get('idempotency-key'))

    @app.get('/api/local/research-native')
    def research_native_list():
        return {'items': [run for run in app.state.service.store.listing('runs')
                          if run['selected_engine'] == 'engine_claude_research_native' and not run.get('parent_run_id')]}

    @app.get('/api/local/research-native/{run_id}')
    def research_native_detail(run_id: str):
        return app.state.service.research_native.detail(run_id)

    @app.get('/research-agents', include_in_schema=False)
    def research_agents_page():
        return FileResponse(ROOT / 'frontend/research-agents.html')

    @app.get('/agent-lab', include_in_schema=False)
    def agent_lab_page():
        return FileResponse(ROOT / 'frontend/agent-lab.html')

    @app.get('/agent-runtime', include_in_schema=False)
    def agent_runtime_page():
        return FileResponse(ROOT / 'frontend/agent-runtime.html')

    @app.get('/connectors/baidu-netdisk', include_in_schema=False)
    def baidu_netdisk_page():
        return FileResponse(ROOT / 'frontend/baidu-netdisk.html')

    @app.post('/api/v1/resources', status_code=201)
    async def upload(request: Request, name: str = 'data.csv'):
        return app.state.service.resource(name, await read_body(request))

    @app.get('/api/v1/resources/{resource_id}')
    def resource(resource_id: str):
        return app.state.service.store.get('resources', resource_id)

    @app.get('/api/local/sample')
    def sample():
        return Response((ROOT / 'examples/sales.csv').read_bytes(), media_type='text/csv', headers={'Content-Disposition': 'attachment; filename="sales.csv"'})

    @app.post('/api/local/intents:interpret')
    async def interpret_intent(request: Request):
        body = await json_body(request)
        if set(body) - {'objective', 'resource_id'}:
            raise Problem('VALIDATION_ERROR', '意图预检只接受 objective 和可选 resource_id。', 422)
        return app.state.service.interpret_intent(body)

    @app.post('/api/local/tasks', status_code=202)
    async def quick_task(request: Request):
        body = await json_body(request)
        if set(body) - {'resource_id', 'objective', 'timeout_seconds'} or not isinstance(body.get('resource_id'), str):
            raise Problem('VALIDATION_ERROR', '请提供 resource_id 和 objective。', 422)
        interpretation = app.state.service.interpret_intent(body)
        if interpretation['decision'] == 'clarification_required':
            raise Problem('INTENT_CLARIFICATION_REQUIRED', interpretation['clarification']['question'], 422)
        if interpretation['decision'] != 'ready':
            raise Problem('INTENT_REJECTED', '当前工作台只支持本地 CSV 分析，请调整目标后重试。', 422)
        return app.state.service.create_task(local_task(body['resource_id'], body.get('objective'), body.get('timeout_seconds', 60)), request.headers.get('idempotency-key'))

    @app.post('/api/v1/tasks', status_code=202)
    async def task_create(request: Request):
        return app.state.service.create_task(await json_body(request), request.headers.get('idempotency-key'))

    @app.get('/api/v1/tasks')
    def tasks():
        store = app.state.service.store
        runs = store.listing('runs')
        return {'items': [{'task': t, 'latest_run': next((r for r in runs if r['task_id'] == t['id'] and not r.get('parent_run_id')), None)} for t in store.listing('tasks')]}

    @app.get('/api/v1/tasks/{task_id}')
    def task_detail(task_id: str):
        store = app.state.service.store
        return {'task': store.get('tasks', task_id), 'runs': [r for r in store.listing('runs') if r['task_id'] == task_id]}

    @app.post('/api/v1/tasks/{task_id}/runs', status_code=202)
    async def rerun(task_id: str, request: Request):
        return app.state.service.rerun(task_id, await json_body(request), request.headers.get('idempotency-key'))

    @app.get('/api/v1/runs/{run_id}')
    def run(run_id: str):
        return app.state.service.store.get('runs', run_id)

    @app.post('/api/v1/runs/{run_id}/replans', status_code=201)
    async def replan_create(run_id: str, request: Request):
        return app.state.service.propose_replan(run_id, await json_body(request), request.headers.get('idempotency-key'))

    @app.get('/api/v1/runs/{run_id}/replans')
    def replan_list(run_id: str):
        return app.state.service.replans(run_id)

    @app.get('/api/v1/replans/{replan_id}')
    def replan_detail(replan_id: str):
        return app.state.service.replan(replan_id)

    @app.post('/api/v1/replans/{replan_id}:try')
    async def replan_try(replan_id: str, request: Request):
        return app.state.service.try_replan(replan_id, await json_body(request), request.headers.get('idempotency-key'))

    @app.post('/api/v1/replans/{replan_id}:confirm', status_code=202)
    async def replan_confirm(replan_id: str, request: Request):
        return app.state.service.confirm_replan(replan_id, await json_body(request), request.headers.get('idempotency-key'))

    @app.post('/api/v1/replans/{replan_id}:cancel')
    async def replan_cancel(replan_id: str, request: Request):
        return app.state.service.cancel_replan(replan_id, await json_body(request), request.headers.get('idempotency-key'))

    @app.post('/api/v1/runs/{run_id}:cancel')
    def cancel(run_id: str):
        return app.state.service.cancel(run_id)

    @app.post('/api/local/runs/{run_id}:restore', status_code=202)
    async def restore(run_id: str, request: Request):
        return app.state.service.restore(run_id, await json_body(request), request.headers.get('idempotency-key'))

    @app.get('/api/local/runs/{run_id}/restore')
    def restore_status(run_id: str):
        return app.state.service.restore_status(run_id)

    @app.get('/api/v1/runs/{run_id}/events')
    def events(run_id: str, after: int = 0):
        if after < 0:
            raise Problem('VALIDATION_ERROR', '游标必须非负。', 422)
        items = app.state.service.store.events(run_id, after)
        return {'items': items, 'next_cursor': items[-1]['sequence'] if items else after}

    @app.get('/api/v1/runs/{run_id}/artifacts')
    def artifact_list(run_id: str):
        return {'items': app.state.service.store.artifact_list(run_id)}

    @app.get('/api/v1/tasks/{task_id}/artifacts')
    def task_artifacts(task_id: str):
        store = app.state.service.store
        store.get('tasks', task_id)
        runs = [r for r in store.listing('runs') if r['task_id'] == task_id]
        return {'items': [a for r in runs for a in store.artifact_list(r['id'])]}

    @app.get('/api/v1/artifacts/{artifact_id}/content')
    def content(artifact_id: str, download: bool = False):
        store = app.state.service.store
        doc = store.get('artifacts', artifact_id)
        with store.lock:
            body = store.db.execute('SELECT body FROM artifacts WHERE id=?', (artifact_id,)).fetchone()[0]
        return Response(body, media_type=doc['media_type'], headers={'Content-Disposition': ('attachment' if download else 'inline') + '; filename="' + doc['name'] + '"'})

    @app.get('/')
    def index():
        return FileResponse(ROOT / 'frontend/index.html')

    @app.get('/docs', include_in_schema=False)
    def api_docs():
        return FileResponse(ROOT / 'frontend/api.html')

    app.mount('/static', StaticFiles(directory=ROOT / 'frontend'), name='static')
    generated = app.openapi()
    generated['paths']['/api/local/research']['post']['requestBody'] = {
        'required': True, 'content': {'application/json': {'schema': json.loads((ROOT / 'specs/v1/research-request.schema.json').read_text())}}}
    research_agents_schema = json.loads((ROOT / 'specs/v1/research-agent-runtime.schema.json').read_text())
    research_agents_definitions = json.loads(json.dumps(research_agents_schema['$defs']).replace('#/$defs/', '#/components/schemas/'))
    generated.setdefault('components', {}).setdefault('schemas', {}).update(research_agents_definitions)
    generated['paths']['/api/local/research-agents']['post']['requestBody'] = {
        'required': True, 'content': {'application/json': {'schema': {'$ref': '#/components/schemas/research_agent_request'}}}}
    native_research_schema = json.loads((ROOT / 'specs/v1/claude-research-runtime.schema.json').read_text())
    native_research_definitions = json.loads(json.dumps(native_research_schema['$defs']).replace('#/$defs/', '#/components/schemas/'))
    generated.setdefault('components', {}).setdefault('schemas', {}).update(native_research_definitions)
    generated['paths']['/api/local/research-native']['post']['requestBody'] = {
        'required': True, 'content': {'application/json': {'schema': {'$ref': '#/components/schemas/native_research_request'}}}}
    generated['paths']['/api/local/research-native']['post'].setdefault('parameters', []).append({
        'in': 'header', 'name': 'Idempotency-Key', 'required': True,
        'schema': {'type': 'string', 'minLength': 1, 'maxLength': 128},
    })
    external_skill_schema = json.loads((ROOT / 'specs/v1/external-skill-runtime.schema.json').read_text())
    external_skill_definitions = json.loads(json.dumps(external_skill_schema['$defs']).replace('#/$defs/', '#/components/schemas/'))
    generated.setdefault('components', {}).setdefault('schemas', {}).update(external_skill_definitions)
    generated['paths']['/api/local/external-skills/packages']['post']['requestBody'] = {
        'required': True, 'content': {'application/zip': {'schema': {'type': 'string', 'format': 'binary'}}}}
    generated['paths']['/api/local/external-skills/packages']['post'].setdefault('parameters', []).append({
        'in': 'header', 'name': 'Idempotency-Key', 'required': True,
        'schema': {'type': 'string', 'minLength': 1, 'maxLength': 128},
    })
    external_execute_path = '/api/local/external-skills/packages/{package_id}:execute'
    generated['paths'][external_execute_path]['post']['requestBody'] = {
        'required': True, 'content': {'application/json': {'schema': {'$ref': '#/components/schemas/execution_request'}}}}
    generated['paths'][external_execute_path]['post']['responses']['200']['content'] = {
        'application/json': {'schema': {'$ref': '#/components/schemas/execution_result'}}}
    generated['paths'][external_execute_path]['post'].setdefault('parameters', []).append({
        'in': 'header', 'name': 'Idempotency-Key', 'required': True,
        'schema': {'type': 'string', 'minLength': 1, 'maxLength': 128},
    })
    memory_schema = json.loads((ROOT / 'specs/v1/memory-plane.schema.json').read_text())
    memory_definitions = json.loads(json.dumps(memory_schema['$defs']).replace('#/$defs/', '#/components/schemas/'))
    generated.setdefault('components', {}).setdefault('schemas', {}).update(memory_definitions)
    generated['paths']['/api/local/memory/banks']['post']['requestBody'] = {
        'required': True, 'content': {'application/json': {'schema': {'$ref': '#/components/schemas/bank_create_request'}}}}
    generated['paths']['/api/local/memory/banks']['post'].setdefault('parameters', []).append({
        'in': 'header', 'name': 'Idempotency-Key', 'required': True,
        'schema': {'type': 'string', 'minLength': 1, 'maxLength': 128},
    })
    memory_retain_path = '/api/local/memory/banks/{bank_id}/retain'
    generated['paths'][memory_retain_path]['post']['requestBody'] = {
        'required': True, 'content': {'application/json': {'schema': {'$ref': '#/components/schemas/retain_request'}}}}
    generated['paths'][memory_retain_path]['post'].setdefault('parameters', []).append({
        'in': 'header', 'name': 'Idempotency-Key', 'required': True,
        'schema': {'type': 'string', 'minLength': 1, 'maxLength': 128},
    })
    memory_graph_schema = json.loads((ROOT / 'specs/v1/memory-graph.schema.json').read_text())
    memory_graph_definitions = json.loads(json.dumps(memory_graph_schema['$defs']).replace('#/$defs/', '#/components/schemas/'))
    generated.setdefault('components', {}).setdefault('schemas', {}).update(memory_graph_definitions)
    for graph_path, definition, response_definition in (
        ('/api/local/memory/banks/{bank_id}/entities', 'entity_input', 'entity_create_result'),
        ('/api/local/memory/banks/{bank_id}/relations', 'relation_input', 'relation_create_result'),
    ):
        generated['paths'][graph_path]['post']['requestBody'] = {
            'required': True, 'content': {'application/json': {'schema': {'$ref': '#/components/schemas/' + definition}}}}
        generated['paths'][graph_path]['post']['responses']['201']['content'] = {
            'application/json': {'schema': {'$ref': '#/components/schemas/' + response_definition}}}
        generated['paths'][graph_path]['post'].setdefault('parameters', []).append({
            'in': 'header', 'name': 'Idempotency-Key', 'required': True,
            'schema': {'type': 'string', 'minLength': 1, 'maxLength': 128},
        })
    memory_recall_path = '/api/local/memory/banks/{bank_id}:recall'
    generated['paths'][memory_recall_path]['post']['requestBody'] = {
        'required': True, 'content': {'application/json': {'schema': {'$ref': '#/components/schemas/recall_request'}}}}
    generated['paths'][memory_recall_path]['post']['responses']['200']['content'] = {
        'application/json': {'schema': {'$ref': '#/components/schemas/evidence_bundle'}}}
    memory_context_schema = json.loads((ROOT / 'specs/v1/memory-context.schema.json').read_text())
    memory_context_definitions = json.loads(json.dumps(memory_context_schema['$defs']).replace('#/$defs/', '#/components/schemas/'))
    generated.setdefault('components', {}).setdefault('schemas', {}).update(memory_context_definitions)
    memory_context_path = '/api/local/memory/banks/{bank_id}:context'
    generated['paths'][memory_context_path]['post']['requestBody'] = {
        'required': True, 'content': {'application/json': {'schema': {'$ref': '#/components/schemas/context_request'}}}}
    generated['paths'][memory_context_path]['post']['responses']['200']['content'] = {
        'application/json': {'schema': {'$ref': '#/components/schemas/context_capsule'}}}
    memory_detail_path = '/api/local/memory/banks/{bank_id}:recall-details'
    generated['paths'][memory_detail_path]['post']['requestBody'] = {
        'required': True, 'content': {'application/json': {'schema': {'$ref': '#/components/schemas/detail_recall_request'}}}}
    generated['paths'][memory_detail_path]['post']['responses']['200']['content'] = {
        'application/json': {'schema': {'$ref': '#/components/schemas/detail_bundle'}}}
    memory_graph_recall_path = '/api/local/memory/banks/{bank_id}:graph-recall'
    generated['paths'][memory_graph_recall_path]['post']['requestBody'] = {
        'required': True, 'content': {'application/json': {'schema': {'$ref': '#/components/schemas/graph_recall_request'}}}}
    generated['paths'][memory_graph_recall_path]['post']['responses']['200']['content'] = {
        'application/json': {'schema': {'$ref': '#/components/schemas/graph_evidence_bundle'}}}
    memory_entity_catalog_schema = json.loads((ROOT / 'specs/v1/memory-entity-catalog.schema.json').read_text())
    memory_entity_catalog_definitions = json.loads(json.dumps(memory_entity_catalog_schema['$defs']).replace('#/$defs/', '#/components/schemas/'))
    generated.setdefault('components', {}).setdefault('schemas', {}).update(memory_entity_catalog_definitions)
    memory_entity_resolve_path = '/api/local/memory/banks/{bank_id}:resolve-entity'
    generated['paths'][memory_entity_resolve_path]['post']['requestBody'] = {
        'required': True, 'content': {'application/json': {'schema': {'$ref': '#/components/schemas/entity_resolve_request'}}}}
    generated['paths'][memory_entity_resolve_path]['post']['responses']['200']['content'] = {
        'application/json': {'schema': {'$ref': '#/components/schemas/entity_resolution'}}}
    memory_lineage_schema = json.loads((ROOT / 'specs/v1/memory-fact-lineage.schema.json').read_text())
    memory_lineage_definitions = json.loads(json.dumps(memory_lineage_schema['$defs']).replace('#/$defs/', '#/components/schemas/'))
    generated.setdefault('components', {}).setdefault('schemas', {}).update(memory_lineage_definitions)
    memory_lineage_path = '/api/local/memory/banks/{bank_id}:fact-lineage'
    generated['paths'][memory_lineage_path]['post']['requestBody'] = {
        'required': True, 'content': {'application/json': {'schema': {'$ref': '#/components/schemas/request'}}}}
    generated['paths'][memory_lineage_path]['post']['responses']['200']['content'] = {
        'application/json': {'schema': {'$ref': '#/components/schemas/bundle'}}}
    memory_retract_path = '/api/local/memory/sources/{source_id}:retract'
    generated['paths'][memory_retract_path]['post'].setdefault('parameters', []).append({
        'in': 'header', 'name': 'Idempotency-Key', 'required': True,
        'schema': {'type': 'string', 'minLength': 1, 'maxLength': 128},
    })
    memory_delete_path = '/api/local/memory/sources/{source_id}'
    generated['paths'][memory_delete_path]['delete'].setdefault('parameters', []).append({
        'in': 'header', 'name': 'Idempotency-Key', 'required': True,
        'schema': {'type': 'string', 'minLength': 1, 'maxLength': 128},
    })
    team_schema = json.loads((ROOT / 'specs/v1/team-coordination.schema.json').read_text())
    team_definitions = json.loads(json.dumps(team_schema['$defs']).replace('#/$defs/', '#/components/schemas/'))
    generated.setdefault('components', {}).setdefault('schemas', {}).update(team_definitions)
    team_post_contracts = (
        ('/api/local/team/tasks', 'team_task_create_request', '201', 'team_task'),
        ('/api/local/team/tasks/{task_id}:claim', 'claim_request', '200', 'team_task'),
        ('/api/local/team/tasks/{task_id}/handoffs', 'handoff_create_request', '201', 'handoff_result'),
        ('/api/local/team/tasks/{task_id}:submit', 'submit_request', '200', 'team_task'),
        ('/api/local/team/tasks/{task_id}/gate-decisions', 'gate_decision_request', '201', 'gate_decision_result'),
    )
    for team_path, request_definition, status, response_definition in team_post_contracts:
        operation = generated['paths'][team_path]['post']
        operation['requestBody'] = {
            'required': True,
            'content': {'application/json': {'schema': {'$ref': '#/components/schemas/' + request_definition}}},
        }
        operation['responses'][status]['content'] = {
            'application/json': {'schema': {'$ref': '#/components/schemas/' + response_definition}}}
        operation.setdefault('parameters', []).append({
            'in': 'header', 'name': 'Idempotency-Key', 'required': True,
            'schema': {'type': 'string', 'minLength': 1, 'maxLength': 128},
        })
    generated['paths']['/api/local/team/runtime']['get']['responses']['200']['content'] = {
        'application/json': {'schema': {'$ref': '#/components/schemas/runtime_status'}}}
    generated['paths']['/api/local/team/tasks']['get']['responses']['200']['content'] = {
        'application/json': {'schema': {'$ref': '#/components/schemas/team_task_list'}}}
    generated['paths']['/api/local/team/tasks/{task_id}']['get']['responses']['200']['content'] = {
        'application/json': {'schema': {'$ref': '#/components/schemas/team_task_detail'}}}
    definitions = json.loads(json.dumps(BUNDLE['$defs']).replace('#/$defs/', '#/components/schemas/'))
    generated.setdefault('components', {}).setdefault('schemas', {}).update(definitions)
    generated['paths']['/api/v1/tasks']['post']['requestBody'] = {
        'required': True, 'content': {'application/json': {'schema': {'$ref': '#/components/schemas/task_create'}}}}
    generated['paths']['/api/local/tasks']['post']['requestBody'] = {
        'required': True, 'content': {'application/json': {'schema': {
            'type': 'object', 'additionalProperties': False, 'required': ['resource_id', 'objective'],
            'properties': {'resource_id': {'type': 'string'}, 'objective': {'type': 'string', 'minLength': 1, 'maxLength': 2000},
                           'timeout_seconds': {'type': 'integer', 'minimum': 1, 'maximum': 300}}}}}}
    intent_schema = json.loads((ROOT / 'specs/v1/intent-contract.schema.json').read_text())
    intent_definitions = json.loads(json.dumps(intent_schema['$defs']).replace('#/$defs/', '#/components/schemas/'))
    generated.setdefault('components', {}).setdefault('schemas', {}).update(intent_definitions)
    generated['paths']['/api/local/intents:interpret']['post']['requestBody'] = {
        'required': True, 'content': {'application/json': {'schema': {
            '$ref': '#/components/schemas/intent_interpret_request'}}}}
    generated['paths']['/api/local/intents:interpret']['post']['responses']['200']['content'] = {
        'application/json': {'schema': {'$ref': '#/components/schemas/intent_interpretation'}}}
    connector_schema = json.loads((ROOT / 'specs/v1/baidu-netdisk-connector.schema.json').read_text())
    generated.setdefault('components', {}).setdefault('schemas', {}).update(connector_schema['$defs'])
    generated['paths']['/api/local/connectors/baidu-netdisk/authorization']['post']['requestBody'] = {
        'required': True, 'content': {'application/json': {'schema': {'type': 'object', 'additionalProperties': False}}}}
    generated['paths']['/api/local/connectors/baidu-netdisk:disconnect']['post']['requestBody'] = {
        'required': True, 'content': {'application/json': {'schema': {'type': 'object', 'additionalProperties': False}}}}
    for path, method, status, schema in (
        ('/api/local/connectors/baidu-netdisk', 'get', '200', 'connection_status'),
        ('/api/local/connectors/baidu-netdisk/authorization', 'post', '201', 'authorization_start'),
        ('/api/local/connectors/baidu-netdisk:disconnect', 'post', '200', 'connection_status'),
    ):
        generated['paths'][path][method]['responses'][status]['content'] = {
            'application/json': {'schema': {'$ref': '#/components/schemas/' + schema}}}
    agent_lab_schema = json.loads((ROOT / 'specs/v1/local-agent-lab.schema.json').read_text())
    agent_lab_definitions = json.loads(json.dumps(agent_lab_schema['$defs']).replace('#/$defs/', '#/components/schemas/'))
    generated.setdefault('components', {}).setdefault('schemas', {}).update(agent_lab_definitions)
    generated['components']['schemas'].update({
        'agent_lab_runtime': {
            'type': 'object', 'additionalProperties': False,
            'required': ['mode', 'model_calls', 'provider_calls', 'network_calls', 'tool_calls', 'tool_binding_count', 'note'],
            'properties': {
                'mode': {'const': 'local_deterministic_demo'}, 'model_calls': {'const': 0},
                'provider_calls': {'const': 0}, 'network_calls': {'const': 0}, 'tool_calls': {'const': 0},
                'tool_binding_count': {'const': 0}, 'note': {'type': 'string'},
            },
        },
    })
    for path, definition in (
        ('/api/local/agent-lab/providers', 'provider_create_request'),
        ('/api/local/agent-lab/models', 'model_create_request'),
        ('/api/local/agent-lab/agents', 'agent_create_request'),
        ('/api/local/agent-lab/sessions', 'session_create_request'),
        ('/api/local/agent-lab/sessions/{session_id}/messages', 'send_message_request'),
    ):
        generated['paths'][path]['post']['requestBody'] = {
            'required': True, 'content': {'application/json': {'schema': {'$ref': '#/components/schemas/' + definition}}}}
        generated['paths'][path]['post'].setdefault('parameters', []).append({
            'in': 'header', 'name': 'Idempotency-Key', 'required': True,
            'schema': {'type': 'string', 'minLength': 1, 'maxLength': 128},
        })
    generated['paths']['/api/local/agent-lab/sessions/{session_id}/messages']['post']['parameters'].append({
        'in': 'header', 'name': 'Accept', 'required': True, 'schema': {'const': 'text/event-stream'},
    })
    generated['paths']['/api/local/agent-lab/sessions/{session_id}/messages']['post']['responses']['200']['content'] = {
        'text/event-stream': {'schema': {'$ref': '#/components/schemas/stream_event'}}}
    runtime_schema = json.loads((ROOT / 'specs/v1/agent-runtime.schema.json').read_text())
    runtime_definitions = json.loads(json.dumps(runtime_schema['$defs']).replace('#/$defs/', '#/components/schemas/'))
    generated.setdefault('components', {}).setdefault('schemas', {}).update(runtime_definitions)
    generated['components']['schemas']['agent_runtime_status'] = {
        'type': 'object', 'additionalProperties': False,
        'required': ['mode', 'runtime_enabled', 'credential_resolution', 'model_calls', 'provider_calls', 'network_calls', 'tool_binding_count', 'note'],
        'properties': {
            'mode': {'const': 'provider_agent_chat_runtime@1'}, 'runtime_enabled': {'type': 'boolean'},
            'credential_resolution': {'const': 'deferred_to_keychain_at_transport_boundary'}, 'model_calls': {'const': 0},
            'provider_calls': {'const': 0}, 'network_calls': {'const': 0}, 'tool_binding_count': {'const': 0}, 'note': {'type': 'string'},
        },
    }
    for path, definition in (
        ('/api/local/agent-runtime/providers', 'provider_create_request'),
        ('/api/local/agent-runtime/models', 'model_create_request'),
        ('/api/local/agent-runtime/agents', 'agent_create_request'),
        ('/api/local/agent-runtime/sessions', 'session_create_request'),
        ('/api/local/agent-runtime/sessions/{session_id}/messages', 'send_message_request'),
    ):
        generated['paths'][path]['post']['requestBody'] = {
            'required': True, 'content': {'application/json': {'schema': {'$ref': '#/components/schemas/' + definition}}}}
        generated['paths'][path]['post'].setdefault('parameters', []).append({
            'in': 'header', 'name': 'Idempotency-Key', 'required': True,
            'schema': {'type': 'string', 'minLength': 1, 'maxLength': 128},
        })
    generated['paths']['/api/local/agent-runtime/sessions/{session_id}/messages']['post']['parameters'].append({
        'in': 'header', 'name': 'Accept', 'required': True, 'schema': {'const': 'text/event-stream'},
    })
    generated['paths']['/api/local/agent-runtime/sessions/{session_id}/messages']['post']['responses']['200']['content'] = {
        'text/event-stream': {'schema': {'$ref': '#/components/schemas/runtime_stream_event'}}}
    restore_schema = json.loads((ROOT / 'specs/v1/local-checkpoint-restore.schema.json').read_text())
    generated.setdefault('components', {}).setdefault('schemas', {}).update(restore_schema['$defs'])
    generated['paths']['/api/local/runs/{run_id}:restore']['post']['requestBody'] = {
        'required': True, 'content': {'application/json': {'schema': {'$ref': '#/components/schemas/restore_request'}}}}
    generated['paths']['/api/local/runs/{run_id}:restore']['post']['responses']['202'] = {
        'description': 'A new, bound recovery Run was queued.',
        'content': {'application/json': {'schema': {'$ref': '#/components/schemas/restore_response'}}}}
    generated['paths']['/api/local/runs/{run_id}/restore']['get']['responses']['200']['content'] = {
        'application/json': {'schema': {'$ref': '#/components/schemas/restore_status'}}}
    control_definitions = json.loads(json.dumps(CONTROL['$defs']).replace('#/$defs/', '#/components/schemas/'))
    generated.setdefault('components', {}).setdefault('schemas', {}).update(control_definitions)
    replan_schema = json.loads((ROOT / 'specs/v1/local-replan.schema.json').read_text())
    generated.setdefault('components', {}).setdefault('schemas', {}).update(replan_schema['$defs'])
    generated['components']['schemas'].update({
        'ReplanList': {
            'type': 'object', 'additionalProperties': False, 'required': ['items'],
            'properties': {'items': {'type': 'array', 'items': {'$ref': '#/components/schemas/replan_created'}}},
        },
        'ReplanDetail': {
            'type': 'object', 'additionalProperties': False, 'required': ['attempt', 'candidate_plan', 'gaps'],
            'properties': {
                'attempt': {'$ref': '#/components/schemas/replan_attempt'},
                'candidate_plan': {'$ref': '#/components/schemas/plan_revision'},
                'gaps': {'type': 'array', 'minItems': 1, 'items': {'$ref': '#/components/schemas/gap'}},
            },
        },
    })
    generated['paths']['/api/v1/runs/{run_id}/replans']['get']['responses']['200']['content'] = {
        'application/json': {'schema': {'$ref': '#/components/schemas/ReplanList'}}}
    generated['paths']['/api/v1/replans/{replan_id}']['get']['responses']['200']['content'] = {
        'application/json': {'schema': {'$ref': '#/components/schemas/ReplanDetail'}}}
    for path, method, status, schema in (
        ('/api/v1/runs/{run_id}/replans', 'post', '201', 'replan_created'),
        ('/api/v1/replans/{replan_id}:try', 'post', '200', 'replan_try_result'),
        ('/api/v1/replans/{replan_id}:confirm', 'post', '202', 'replan_confirmed'),
        ('/api/v1/replans/{replan_id}:cancel', 'post', '200', 'replan_cancelled'),
    ):
        generated['paths'][path][method]['requestBody'] = {
            'required': True, 'content': {'application/json': {'schema': {'$ref': '#/components/schemas/empty_request'}}}}
        generated['paths'][path][method]['responses'][status]['content'] = {
            'application/json': {'schema': {'$ref': '#/components/schemas/' + schema}}}
    for path in ('/api/v1/tasks', '/api/local/tasks', '/api/v1/tasks/{task_id}/runs', '/api/local/research', '/api/local/research-agents',
                 '/api/local/runs/{run_id}:restore', '/api/local/connectors/baidu-netdisk/authorization',
                 '/api/local/connectors/baidu-netdisk:disconnect', '/api/v1/runs/{run_id}/replans',
                 '/api/v1/replans/{replan_id}:try', '/api/v1/replans/{replan_id}:confirm',
                 '/api/v1/replans/{replan_id}:cancel'):
        generated['paths'][path]['post'].setdefault('parameters', []).append({
            'in': 'header', 'name': 'Idempotency-Key', 'required': True, 'schema': {'type': 'string', 'minLength': 1, 'maxLength': 128}})
    return app


app = create_app()
