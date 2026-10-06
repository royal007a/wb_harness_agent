"""Read-only synthetic browser diagnostics; no changed assertions/timeouts."""
import time
import pytest


@pytest.hookimpl(hookwrapper=True)
def pytest_fixture_setup(fixturedef, request):
    outcome = yield
    if fixturedef.argname != 'ui' or outcome.excinfo:
        return
    page, _, _, base = outcome.get_result()
    started = time.monotonic()
    def log(kind, value=''):
        print('UI_NETWORK', request.node.nodeid, round(time.monotonic() - started, 3), kind, value, flush=True)
    page.on('request', lambda req: log('request', req.method + ' ' + req.url.replace(base, '<loopback>')))
    page.on('response', lambda res: log('response', str(res.status) + ' ' + res.url.replace(base, '<loopback>')))
    page.on('requestfinished', lambda req: log('finished', req.url.replace(base, '<loopback>')))
    page.on('requestfailed', lambda req: log('failed', req.url.replace(base, '<loopback>') + ' ' + str(req.failure)))
    page.on('domcontentloaded', lambda: log('domcontentloaded'))
    page.on('load', lambda: log('load'))
    page.on('crash', lambda: log('crash'))
    page.on('close', lambda: log('close'))
