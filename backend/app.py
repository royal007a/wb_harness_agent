"""HTTP transport for the trusted local-user workbench."""
import asyncio
import fcntl
import json
import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles

from .analysis import MAX_BYTES, Problem
from .service import BUNDLE, ROOT, Service, local_task
from .store import Store, uid


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
        if request.headers.get('sec-fetch-site') == 'cross-site':
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
            {'id': 'engine_smolagents_code', 'name': 'Smolagents', 'status': 'planned', 'description': 'CodeAct · 等待远程沙箱探针'},
            {'id': 'engine_claude', 'name': 'Claude Agent SDK', 'status': 'planned', 'description': '研报与复杂编排 · P1'},
            {'id': 'engine_deepagents', 'name': 'Deep Agents', 'status': 'planned', 'description': '动态知识与记忆 · P2'},
            {'id': 'engine_pi', 'name': 'Pi', 'status': 'planned', 'description': 'TypeScript 审查 · P2'}]}

    @app.get('/api/v1/resources')
    def resources():
        return {'items': app.state.service.store.listing('resources')}

    @app.post('/api/v1/resources', status_code=201)
    async def upload(request: Request, name: str = 'data.csv'):
        return app.state.service.resource(name, await read_body(request))

    @app.get('/api/v1/resources/{resource_id}')
    def resource(resource_id: str):
        return app.state.service.store.get('resources', resource_id)

    @app.get('/api/local/sample')
    def sample():
        return Response((ROOT / 'examples/sales.csv').read_bytes(), media_type='text/csv', headers={'Content-Disposition': 'attachment; filename="sales.csv"'})

    @app.post('/api/local/tasks', status_code=202)
    async def quick_task(request: Request):
        body = await json_body(request)
        if set(body) - {'resource_id', 'objective', 'timeout_seconds'} or not isinstance(body.get('resource_id'), str):
            raise Problem('VALIDATION_ERROR', '请提供 resource_id 和 objective。', 422)
        return app.state.service.create_task(local_task(body['resource_id'], body.get('objective'), body.get('timeout_seconds', 60)), request.headers.get('idempotency-key'))

    @app.post('/api/v1/tasks', status_code=202)
    async def task_create(request: Request):
        return app.state.service.create_task(await json_body(request), request.headers.get('idempotency-key'))

    @app.get('/api/v1/tasks')
    def tasks():
        store = app.state.service.store
        runs = store.listing('runs')
        return {'items': [{'task': t, 'latest_run': next((r for r in runs if r['task_id'] == t['id']), None)} for t in store.listing('tasks')]}

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

    @app.post('/api/v1/runs/{run_id}:cancel')
    def cancel(run_id: str):
        return app.state.service.cancel(run_id)

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
    definitions = json.loads(json.dumps(BUNDLE['$defs']).replace('#/$defs/', '#/components/schemas/'))
    generated.setdefault('components', {}).setdefault('schemas', {}).update(definitions)
    generated['paths']['/api/v1/tasks']['post']['requestBody'] = {
        'required': True, 'content': {'application/json': {'schema': {'$ref': '#/components/schemas/task_create'}}}}
    generated['paths']['/api/local/tasks']['post']['requestBody'] = {
        'required': True, 'content': {'application/json': {'schema': {
            'type': 'object', 'additionalProperties': False, 'required': ['resource_id', 'objective'],
            'properties': {'resource_id': {'type': 'string'}, 'objective': {'type': 'string', 'minLength': 1, 'maxLength': 2000},
                           'timeout_seconds': {'type': 'integer', 'minimum': 1, 'maximum': 300}}}}}}
    for path in ('/api/v1/tasks', '/api/local/tasks', '/api/v1/tasks/{task_id}/runs'):
        generated['paths'][path]['post'].setdefault('parameters', []).append({
            'in': 'header', 'name': 'Idempotency-Key', 'required': True, 'schema': {'type': 'string', 'minLength': 1, 'maxLength': 128}})
    return app


app = create_app()
