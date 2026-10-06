"""Log headers/body completion, never request or response content."""
import time
import uvicorn
import pytest

_server_init = uvicorn.Server.__init__


class Observe:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope['type'] != 'http':
            return await self.app(scope, receive, send)
        started = time.monotonic()
        path = scope['path']
        print('ASGI_BEGIN', round(started, 3), path, flush=True)
        async def observed(message):
            await send(message)
            kind = message['type']
            if kind == 'http.response.start':
                print('ASGI_HEADERS', round(time.monotonic(), 3), path, message['status'], flush=True)
            elif kind == 'http.response.body' and not message.get('more_body', False):
                print('ASGI_FINISH', round(time.monotonic(), 3), path,
                      'elapsed', round(time.monotonic() - started, 3), flush=True)
        return await self.app(scope, receive, observed)


def initialize(self, config):
    config.app = Observe(config.app)
    _server_init(self, config)


@pytest.hookimpl(hookwrapper=True)
def pytest_fixture_setup(fixturedef, request):
    if fixturedef.argname != 'ui':
        yield
        return
    uvicorn.Server.__init__ = initialize
    try:
        yield
    finally:
        uvicorn.Server.__init__ = _server_init
