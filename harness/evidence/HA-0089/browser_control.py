"""Empty-page loopback control: diagnostic only, never substitutes for product tests."""
import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.request import urlopen
from playwright.sync_api import sync_playwright, Error

class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        body = b'<!doctype html><html><body><button id="b">control</button></body></html>'
        self.send_response(200)
        self.send_header('Content-Type', 'text/html')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)
    def log_message(self, *args):
        pass

server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
thread = threading.Thread(target=server.serve_forever, daemon=True)
thread.start()
url = 'http://127.0.0.1:' + str(server.server_address[1])
try:
    with sync_playwright() as p:
        start = time.monotonic()
        browser = p.chromium.launch()
        print(json.dumps({'launch_s': time.monotonic() - start}), flush=True)
        try:
            page = browser.new_page()
            for sample in range(3):
                start = time.monotonic()
                with urlopen(url, timeout=30) as response:
                    assert response.read().startswith(b'<!doctype')
                print(json.dumps({'sample': sample, 'http_s': time.monotonic() - start}), flush=True)
                for name, action in [('goto', lambda: page.goto(url)),
                                     ('click', lambda: page.locator('#b').click()),
                                     ('evaluate', lambda: page.evaluate('1 + 1'))]:
                    start = time.monotonic()
                    try:
                        action()
                        status = 'ok'
                    except Error as exc:
                        status = type(exc).__name__
                    print(json.dumps({'sample': sample, 'operation': name,
                                      'status': status, 'elapsed_s': time.monotonic() - start}), flush=True)
        finally:
            browser.close()
finally:
    server.shutdown()
    server.server_close()
    thread.join(2)
