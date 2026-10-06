"""Private observation only: no timeout/assertion/transport changes."""
import json
import threading
import time

import pytest


@pytest.hookimpl(hookwrapper=True)
def pytest_fixture_setup(fixturedef, request):
    outcome = yield
    if fixturedef.argname != 'ui' or outcome.excinfo:
        return
    page = outcome.get_result()[0]
    stopped = threading.Event()
    gaps = []
    def clock():
        previous = time.monotonic()
        while not stopped.wait(.1):
            current = time.monotonic()
            gaps.append(current - previous)
            previous = current
    thread = threading.Thread(target=clock, daemon=True)
    thread.start()
    def end_clock():
        stopped.set()
        thread.join(1)
        print('PY_CLOCK', json.dumps({'samples': len(gaps), 'max_gap_s': max(gaps, default=0)}), flush=True)
    request.addfinalizer(end_clock)
    page.add_init_script('''(() => {
      const d = window.__clockDiagnostic = {clicks: [], gaps: []};
      let prev = performance.now();
      setInterval(() => {
        const t = performance.now();
        if (t-prev > 250) d.gaps.push(t-prev);
        prev = t;
      }, 100);
      for (const name of ['pointerdown','pointerup','click']) {
        document.addEventListener(name, (e) => {
          if (e.target.closest('button[data-session]')) d.clicks.push({type:name, at:performance.now()});
        }, true);
      }
    })();''')


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item, call):
    outcome = yield
    report = outcome.get_result()
    if report.when != 'call' or 'ui' not in item.funcargs:
        return
    page = item.funcargs['ui'][0]
    start = time.monotonic()
    data = page.evaluate('''() => ({
      timeOrigin: performance.timeOrigin,
      now: performance.now(),
      clicks: window.__clockDiagnostic?.clicks,
      gaps: window.__clockDiagnostic?.gaps,
      resources: performance.getEntriesByType('resource').map(r => ({
        path: new URL(r.name).pathname.replace(/rts_[a-z0-9]+/g,'<session>').replace(/rtp_[a-z0-9]+/g,'<provider>'),
        start: r.startTime, end: r.responseEnd, duration: r.duration
      }))
    })''')
    data['snapshot_roundtrip_s'] = time.monotonic() - start
    data['python_wall_ms'] = time.time()*1000
    data['failed'] = report.failed
    print('BROWSER_CLOCK', json.dumps(data, sort_keys=True), flush=True)
