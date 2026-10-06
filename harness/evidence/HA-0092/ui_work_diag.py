"""Observe browser work vs elapsed time; retain original tests and deadlines."""
import json
import time
import pytest

KEEP = {'Timestamp', 'TaskDuration', 'ScriptDuration', 'LayoutDuration',
        'RecalcStyleDuration', 'JSHeapUsedSize', 'Frames', 'Documents'}

@pytest.hookimpl(hookwrapper=True)
def pytest_fixture_setup(fixturedef, request):
    outcome = yield
    if fixturedef.argname != 'ui' or outcome.excinfo:
        return
    page = outcome.get_result()[0]
    cdp = page.context.new_cdp_session(page)
    cdp.send('Performance.enable')
    before = {x['name']: x['value'] for x in cdp.send('Performance.getMetrics')['metrics'] if x['name'] in KEEP}
    request.node._ui_work_diag = (cdp, before, time.monotonic())
    page.add_init_script('''(() => {
      window.__workDiagnostic = {longTasks: [], supported: false};
      try {
        const observer = new PerformanceObserver((list) => {
          for (const t of list.getEntries()) {
            if (window.__workDiagnostic.longTasks.length < 100)
              window.__workDiagnostic.longTasks.push({start:t.startTime, duration:t.duration});
          }
        });
        observer.observe({type:'longtask', buffered:true});
        window.__workDiagnostic.supported = true;
      } catch (_) {}
    })();''')

@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item, call):
    outcome = yield
    report = outcome.get_result()
    if report.when != 'call' or not hasattr(item, '_ui_work_diag'):
        return
    cdp, before, started = item._ui_work_diag
    page = item.funcargs['ui'][0]
    try:
        after = {x['name']: x['value'] for x in cdp.send('Performance.getMetrics')['metrics'] if x['name'] in KEEP}
        page_work = page.evaluate('''() => ({
          visibility: document.visibilityState,
          longTasks: window.__workDiagnostic?.longTasks,
          supported: window.__workDiagnostic?.supported
        })''')
        print('UI_WORK', json.dumps({'test':item.nodeid, 'failed':report.failed,
              'elapsed':time.monotonic()-started, 'before':before, 'after':after,
              'page':page_work}, sort_keys=True), flush=True)
    except Exception as exc:
        print('UI_WORK_UNAVAILABLE', type(exc).__name__, flush=True)
