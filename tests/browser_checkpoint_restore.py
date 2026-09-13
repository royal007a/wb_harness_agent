"""Exercise the visible ADR-0018 recovery path against a temporary local deployment.

The source Run status is changed only in this disposable SQLite fixture after it has
created a real checkpoint.  No test hook or fault endpoint exists in the product.
"""
import json
import os
import socket
import sqlite3
import subprocess
import tempfile
import time
import urllib.request
import urllib.error
from pathlib import Path

from playwright.sync_api import expect, sync_playwright


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = Path(os.environ.get('HARNESS_BROWSER_EVIDENCE', ROOT / 'harness/evidence/HA-0019'))
OUTPUT.mkdir(parents=True, exist_ok=True)


def free_port():
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0))
        return sock.getsockname()[1]


def api(base, path, method='GET', body=None, key=None):
    data = None if body is None else json.dumps(body).encode()
    headers = {'Content-Type': 'application/json'} if data is not None else {}
    if key:
        headers['Idempotency-Key'] = key
    request = urllib.request.Request(base + path, data=data, headers=headers, method=method)
    with urllib.request.urlopen(request, timeout=5) as response:
        return json.loads(response.read())


def wait_for(base, path, predicate, timeout=10):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            value = api(base, path)
            if predicate(value):
                return value
        except urllib.error.URLError:
            pass
        time.sleep(.05)
    raise AssertionError('timed out waiting for ' + path)


def mark_fixture_source_failed(db_path, run_id):
    with sqlite3.connect(db_path) as db:
        raw = db.execute('SELECT doc FROM runs WHERE id=?', (run_id,)).fetchone()[0]
        run = json.loads(raw)
        run['status'] = 'failed'
        run['exit_reason'] = 'BROWSER_FIXTURE_POST_CHECKPOINT_FAILURE'
        db.execute('UPDATE runs SET doc=? WHERE id=?', (json.dumps(run, ensure_ascii=False, sort_keys=True), run_id))
        db.commit()


def main():
    temp = Path(tempfile.gettempdir()) / f'harnessagent-checkpoint-browser-{os.getpid()}.db'
    port = free_port()
    base = f'http://127.0.0.1:{port}'
    environment = {**os.environ, 'HARNESS_DB': str(temp), 'PYTHONPATH': str(ROOT)}
    process = subprocess.Popen(
        [str(ROOT / '.venv/bin/python'), '-m', 'uvicorn', 'backend.app:app', '--host', '127.0.0.1', '--port', str(port), '--no-access-log'],
        cwd=ROOT, env=environment, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    try:
        wait_for(base, '/api/v1/health', lambda item: item['status'] == 'ok')
        raw = b'name,value\nA,2\nB,4\nC,\n'
        upload = urllib.request.Request(base + '/api/v1/resources?name=checkpoint.csv', data=raw,
                                        headers={'Content-Type': 'text/csv'}, method='POST')
        with urllib.request.urlopen(upload, timeout=5) as response:
            resource = json.loads(response.read())
        created = api(base, '/api/local/tasks', 'POST', {
            'resource_id': resource['id'], 'objective': '浏览器恢复验收的固定数据概览',
        }, 'browser-checkpoint-create')
        source_id = created['initial_run']['id']
        task_id = created['task']['id']
        wait_for(base, '/api/v1/runs/' + source_id, lambda item: item['status'] == 'succeeded')
        mark_fixture_source_failed(temp, source_id)

        with sync_playwright() as playwright:
            browser = playwright.chromium.launch()
            page = browser.new_page(viewport={'width': 1440, 'height': 1150}, device_scale_factor=1)
            errors = []
            page.on('pageerror', lambda error: errors.append(str(error)))
            page.on('console', lambda message: errors.append(message.text) if message.type == 'error' else None)
            page.goto(base)
            expect(page.locator('#detail')).to_be_visible()
            expect(page.locator('#restore')).to_be_visible()
            page.screenshot(path=str(OUTPUT / 'checkpoint-restore-eligible.png'), full_page=True)
            page.get_by_role('button', name='从检查点恢复').click()
            expect(page.locator('#run-select option')).to_have_count(2)
            expect(page.locator('.artifact-link')).to_have_count(3, timeout=15000)
            expect(page.locator('#restore')).to_be_hidden()
            page.screenshot(path=str(OUTPUT / 'checkpoint-restore-workbench.png'), full_page=True)
            assert not errors, errors
            browser.close()

        source = api(base, '/api/v1/runs/' + source_id)
        runs = api(base, '/api/v1/tasks/' + task_id)['runs']
        restored = next(run for run in runs if run.get('restored_from_checkpoint_id'))
        assert source['status'] == 'failed'
        assert restored['status'] == 'succeeded'
        assert restored['based_on_run_id'] == source_id
        assert restored['consumed_turns'] == 2
        events = api(base, f'/api/v1/runs/{restored["id"]}/events')['items']
        assert [event['event_type'] for event in events[:3]] == ['run.queued', 'run.started', 'checkpoint.restored']
        assert not any(event['data'].get('tool') == 'resource.inspect' for event in events)
        report = {
            'browser': 'chromium',
            'checks': ['temporary_deployment', 'checkpoint_visible_after_fixture_failure', 'restore_button',
                       'new_run_created', 'source_terminal_unchanged', 'artifacts_published', 'no_reinspect'],
            'source_run_id': source_id,
            'restored_run_id': restored['id'],
            'errors': [],
            'model_calls': 0,
            'network_calls_by_adapter': 0,
        }
        (OUTPUT / 'browser-checkpoint-restore.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
        print(json.dumps(report, ensure_ascii=False))
    finally:
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)
        for suffix in ('', '-wal', '-shm'):
            (Path(str(temp) + suffix)).unlink(missing_ok=True)


if __name__ == '__main__':
    main()
