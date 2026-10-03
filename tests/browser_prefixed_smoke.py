"""Browser regression against an isolated loopback /harness reverse proxy.

Models nginx's prefix stripping and header rewriting. It deliberately does not
serve root /static or /api. Not evidence of public Basic-password authentication.
HARNESS_UPSTREAM may be a loopback SSH tunnel to the deployed backend.
"""
import http.client
import os
import subprocess
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit


upstream = urlsplit(os.environ.get('HARNESS_UPSTREAM', 'http://127.0.0.1:8765'))
assert upstream.scheme == 'http' and upstream.hostname == '127.0.0.1'


class Proxy(BaseHTTPRequestHandler):
    def log_message(self, *_):
        pass

    def proxy(self):
        if not self.path.startswith('/harness/'):
            self.send_error(404)
            return
        headers = {key: value for key, value in self.headers.items()
                   if key.lower() not in {'host', 'origin', 'connection', 'x-forwarded-prefix'}}
        headers['Host'] = '127.0.0.1:8765'
        headers['X-Forwarded-Prefix'] = '/harness'
        body = self.rfile.read(int(self.headers.get('Content-Length', 0)))
        connection = http.client.HTTPConnection(upstream.hostname, upstream.port, timeout=30)
        try:
            connection.request(self.command, self.path[len('/harness'):], body, headers)
            response = connection.getresponse()
            data = response.read()
            self.send_response(response.status)
            for key, value in response.getheaders():
                if key.lower() not in {'connection', 'transfer-encoding', 'content-length'}:
                    self.send_header(key, value)
            self.send_header('Content-Length', str(len(data)))
            self.end_headers()
            self.wfile.write(data)
        finally:
            connection.close()

    do_GET = proxy
    do_POST = proxy


server = ThreadingHTTPServer(('127.0.0.1', 0), Proxy)
thread = threading.Thread(target=server.serve_forever, daemon=True)
thread.start()
try:
    env = dict(os.environ, HARNESS_TEST_URL=f'http://127.0.0.1:{server.server_port}/harness/')
    script = sys.argv[1] if len(sys.argv) > 1 else 'tests/browser_smoke.py'
    assert script in {'tests/browser_smoke.py', 'tests/browser_agent_lab.py', 'tests/browser_agent_runtime.py'}
    if script != 'tests/browser_smoke.py':
        env['HARNESS_TEST_URL'] = env['HARNESS_TEST_URL'].rstrip('/')
    subprocess.run([sys.executable, script], env=env, check=True)
finally:
    server.shutdown()
    server.server_close()
