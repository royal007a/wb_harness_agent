"""Protocol/lifecycle bridge to the pinned official DSH SDK. No database access."""
from __future__ import annotations

import hmac
import json
import os
from pathlib import Path
import secrets
import selectors
import shutil
import signal
import subprocess
import tempfile
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from backend.analysis import Problem

ROOT = Path(__file__).resolve().parents[1]


class DshAdapter:
    def run(self, prompt, runtime_root, model, model_call, tool_call, emit, check, *, output_limit=2048):
        root = Path(runtime_root).resolve()
        root.mkdir(parents=True, exist_ok=True, mode=0o700)
        workspace = Path(tempfile.mkdtemp(prefix='run-', dir=root))
        workspace.chmod(0o700)
        for name in ('home', 'work', 'tmp'):
            (workspace / name).mkdir(mode=0o700)
        capability = secrets.token_urlsafe(32)
        errors = []
        serial = threading.Lock()

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def do_POST(self):
                try:
                    if not hmac.compare_digest(self.headers.get('Authorization', ''), 'Bearer ' + capability):
                        raise Problem('DSH_GATEWAY_AUTH', '拒绝未授权调用。', 403)
                    if self.path not in ('/model', '/tool') or self.headers.get('Transfer-Encoding'):
                        raise Problem('DSH_GATEWAY_PROTOCOL', '网关协议无效。', 422)
                    size = int(self.headers.get('Content-Length', '-1'))
                    if not 0 < size <= 256 * 1024:
                        raise Problem('DSH_GATEWAY_LIMIT', '网关请求越限。', 422)
                    self.connection.settimeout(5)
                    raw = self.rfile.read(size)
                    if len(raw) != size:
                        raise Problem('DSH_GATEWAY_PROTOCOL', '网关协议无效。', 422)
                    body = json.loads(raw)
                    with serial:
                        if errors:
                            raise errors[0]
                        check()
                        value = (model_call if self.path == '/model' else tool_call)(body)
                        check()
                    encoded = json.dumps(value, ensure_ascii=False, allow_nan=False).encode()
                    self.send_response(200)
                except Exception as exc:
                    errors.append(exc if isinstance(exc, Problem) else Problem('DSH_GATEWAY_FAILED', '平台网关失败。', 502))
                    encoded = b'{"error":"DSH_GATEWAY_REJECTED"}'
                    self.send_response(409)
                self.send_header('Content-Type', 'application/json')
                self.send_header('Content-Length', str(len(encoded)))
                self.end_headers()
                try:
                    self.wfile.write(encoded)
                except (BrokenPipeError, ConnectionResetError):
                    pass

        server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        server.daemon_threads = False
        thread = threading.Thread(target=lambda: server.serve_forever(poll_interval=.1), daemon=True)
        thread.start()
        node = shutil.which('node')
        if not node:
            server.shutdown(); server.server_close()
            raise Problem('DSH_DEPENDENCY_MISSING', '需要 Node 22 和固定版本 DSH。', 503)
        env = {'PATH': str(Path(node).parent) + ':/usr/bin:/bin', 'HOME': str(workspace / 'home'),
               'TMPDIR': str(workspace / 'tmp'), 'HARNESS_DSH_MODEL': model,
               'HARNESS_DSH_GATEWAY': f'http://127.0.0.1:{server.server_port}',
               'HARNESS_DSH_CAPABILITY': capability}
        process = None
        result = None
        try:
            check()
            process = subprocess.Popen([node, str(ROOT / 'dsh-adapter/bridge.mjs')],
                stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                cwd=workspace / 'work', env=env, start_new_session=True)
            job = {'prompt': prompt, 'home': str(workspace / 'home'), 'cwd': str(workspace / 'work'),
                   'max_output_tokens': output_limit}
            process.stdin.write((json.dumps(job) + '\n').encode())
            process.stdin.close()
            buffer = bytearray()
            total = 0
            with selectors.DefaultSelector() as selector:
                selector.register(process.stdout, selectors.EVENT_READ)
                while True:
                    check()
                    if errors:
                        raise errors[0]
                    ready = selector.select(.1)
                    if not ready:
                        if process.poll() is not None:
                            break
                        continue
                    data = os.read(process.stdout.fileno(), 8192)
                    if not data:
                        break
                    total += len(data)
                    buffer.extend(data)
                    if total > 2 * 1024 * 1024 or len(buffer) > 128 * 1024:
                        raise Problem('DSH_OUTPUT_LIMIT', 'DSH 输出越限。', 502)
                    while b'\n' in buffer:
                        line, _, rest = buffer.partition(b'\n')
                        buffer = bytearray(rest)
                        value = json.loads(line)
                        if value.get('type') == 'observation':
                            emit(value)
                        elif value.get('type') == 'result' and result is None:
                            result = value
                        else:
                            raise Problem('DSH_RUNTIME_FAILED', 'DSH 未正常完成。', 502)
            process.wait(timeout=5)
            check()
            if errors:
                raise errors[0]
            if process.returncode or buffer or result is None:
                raise Problem('DSH_RUNTIME_FAILED', 'DSH 未正常完成。', 502)
            return result
        finally:
            if process is not None:
                # Own process group, never a PID obtained from untrusted input.
                try:
                    os.killpg(process.pid, signal.SIGTERM)
                except ProcessLookupError:
                    pass
                try:
                    process.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    os.killpg(process.pid, signal.SIGKILL)
                    process.wait(timeout=3)
                # Reap any SDK child left after the bridge exited.
                try:
                    os.killpg(process.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                if process.stdout:
                    process.stdout.close()
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)
            # Only this mkdtemp-created directory; no shared DSH/Claude home.
            shutil.rmtree(workspace)
