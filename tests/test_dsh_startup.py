"""HA-0086: offline SDK phases and real child-process protocol; no Provider."""
import json
from pathlib import Path
import subprocess
import sys
import time

import pytest

from adapters import dsh
from backend.analysis import Problem
from backend.app import create_app
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]


def test_sdk_phase_classification_no_retry_or_error_content():
    script = r'''
import assert from 'node:assert/strict';
import { RequestTimeoutError } from '@deepseek-ai/dsh-sdk-client';
import { INITIALIZE_TIMEOUT_MS, runWithPhases } from './lifecycle.mjs';
assert.equal(INITIALIZE_TIMEOUT_MS, 60000);
for (const phase of ['start', 'run']) {
  for (const error of [new RequestTimeoutError('SYNTH_PRIVATE'), new Error('SYNTH_PRIVATE'),
      Object.assign(new Error('SYNTH_PRIVATE'), {name: 'RequestTimeoutError'})]) {
    const calls = [];
    const harness = {
      async start() { calls.push('start'); if (phase === 'start') throw error; },
      async run() { calls.push('run'); throw error; },
    };
    await assert.rejects(runWithPhases(harness, 'prompt', {}), e => {
      assert.equal(e.code, phase === 'run' ? 'DSH_RUNTIME_FAILED'
        : error instanceof RequestTimeoutError ? 'DSH_INITIALIZATION_TIMEOUT' : 'DSH_INITIALIZATION_FAILED');
      assert.ok(!String(e.stack).includes('SYNTH_PRIVATE'));
      assert.equal(e.cause, undefined);
      return true;
    });
    assert.deepEqual(calls, phase === 'start' ? ['start'] : ['start', 'run']);
  }
}
const calls = [], options = {onNotification() {}}, result = {finalResponse: 'ok'};
assert.equal(await runWithPhases({async start() {calls.push('start');},
  async run(prompt, received) {calls.push('run'); assert.equal(prompt, 'p');
    assert.equal(received, options); return result;}}, 'p', options), result);
assert.deepEqual(calls, ['start', 'run']);
'''
    result = subprocess.run(['node', '--input-type=module', '-e', script],
                            cwd=ROOT / 'dsh-adapter', capture_output=True, text=True, timeout=20)
    assert result.returncode == 0, result.stderr


def child_bridge(monkeypatch, script):
    original = subprocess.Popen
    children = []
    def spawn(argv, **kwargs):
        child = original([sys.executable, '-c', script], **kwargs)
        children.append(child)
        return child
    monkeypatch.setattr(dsh.subprocess, 'Popen', spawn)
    return children


def run_adapter(root, check=lambda: None, model_call=None):
    def forbidden(*args):
        pytest.fail('startup path must not invoke tools/models or emit observations')
    return dsh.DshAdapter().run('SYNTH_STARTUP_ONLY', root, 'probe', model_call or forbidden,
                                forbidden, forbidden, check)


@pytest.mark.parametrize('code,status', [
    ('DSH_INITIALIZATION_TIMEOUT', 504), ('DSH_INITIALIZATION_FAILED', 502),
    ('DSH_RUNTIME_FAILED', 502), ('DSH_CANCELLED', 409),
])
def test_fixed_child_error_and_cleanup(tmp_path, monkeypatch, code, status):
    body = json.dumps({'type': 'error', 'code': code})
    children = child_bridge(monkeypatch, f'import sys; sys.stdin.readline(); print({body!r}, flush=True)')
    root = tmp_path.resolve() / 'owned'
    with pytest.raises(Problem) as caught:
        run_adapter(root)
    assert (caught.value.code, caught.value.status) == (code, status)
    assert len(children) == 1 and children[0].poll() is not None
    assert not list(root.glob('run-*'))


@pytest.mark.parametrize('body', [
    {'type': 'error', 'code': 'DSH_INITIALIZATION_TIMEOUT', 'message': 'SYNTH_PRIVATE'},
    {'type': 'error', 'code': 'DSH_INITIALIZATION_TIMEOUT', 'stack': 'SYNTH_PRIVATE'},
    {'type': 'error', 'code': 'SYNTH_PRIVATE'}, {'type': 'error', 'code': []},
    {'type': 'error'}, [],
])
def test_untrusted_error_envelope_does_not_forward_fields(tmp_path, monkeypatch, body):
    encoded = json.dumps(body)
    child_bridge(monkeypatch, f'import sys; sys.stdin.readline(); print({encoded!r}, flush=True)')
    with pytest.raises(Problem) as caught:
        run_adapter(tmp_path.resolve() / 'owned')
    assert caught.value.code == 'DSH_RUNTIME_FAILED'
    assert 'SYNTH_PRIVATE' not in str(caught.value)


@pytest.mark.parametrize('code', ['RUN_CANCELLED', 'RUN_TIMEOUT'])
def test_run_check_stops_child_during_startup(tmp_path, monkeypatch, code):
    children = child_bridge(monkeypatch, 'import sys,time; sys.stdin.readline(); time.sleep(60)')
    root = tmp_path.resolve() / 'owned'
    checks_after_spawn = []
    def check():
        if children:
            checks_after_spawn.append(1)
            if len(checks_after_spawn) >= 2:
                raise Problem(code, 'fixed run check', 409)
    before = time.monotonic()
    with pytest.raises(Problem) as caught:
        run_adapter(root, check)
    assert caught.value.code == code
    assert time.monotonic() - before < 5
    assert len(children) == 1 and children[0].poll() is not None
    assert not list(root.glob('run-*'))


def test_gateway_error_takes_priority_over_child_initialization_code(tmp_path, monkeypatch):
    script = r'''
import json,os,sys,urllib.request,urllib.error
sys.stdin.readline()
request = urllib.request.Request(os.environ['HARNESS_DSH_GATEWAY'] + '/model',
    data=b'{}', headers={'Authorization': 'Bearer ' + os.environ['HARNESS_DSH_CAPABILITY']})
try:
    urllib.request.build_opener(urllib.request.ProxyHandler({})).open(request)
except urllib.error.HTTPError:
    pass
print(json.dumps({'type': 'error', 'code': 'DSH_INITIALIZATION_FAILED'}), flush=True)
'''
    child_bridge(monkeypatch, script)
    calls = []
    def model_call(body):
        calls.append(body)
        raise Problem('BUSINESS_TOKEN_BUDGET_EXHAUSTED', 'fixed budget failure', 409)
    with pytest.raises(Problem) as caught:
        run_adapter(tmp_path.resolve() / 'owned', model_call=model_call)
    assert caught.value.code == 'BUSINESS_TOKEN_BUDGET_EXHAUSTED'
    assert calls == [{}]


@pytest.mark.parametrize('code', ['DSH_INITIALIZATION_TIMEOUT', 'DSH_INITIALIZATION_FAILED'])
def test_startup_failure_has_no_model_spend_or_artifacts(tmp_path, monkeypatch, code):
    monkeypatch.setenv('HARNESS_DSH_LOCAL', 'enabled')
    monkeypatch.setenv('HARNESS_DSH_RUN_ROOT', str(tmp_path.resolve() / 'owned'))
    monkeypatch.delenv('HARNESS_DSH_REAL_ENABLED', raising=False)
    # Construct app before replacing Popen: release lookup legitimately uses git.
    with TestClient(create_app(tmp_path / 'test.db', run_worker=False), base_url='http://localhost') as client:
        rt = client.app.state.service.dsh
        ident = rt.create(dict(objective='付款核对', document='甲方30天付款。',
                              public_data_confirmed=True, mode='integration_probe'),
                          'startup-fail')['initial_run']['id']
        body = json.dumps({'type': 'error', 'code': code})
        children = child_bridge(monkeypatch, f'import sys; sys.stdin.readline(); print({body!r}, flush=True)')
        rt.execute(ident)
        result = rt.detail(ident)
        assert result['run']['status'] == 'failed'
        assert result['run']['exit_reason'] == code
        assert result['artifacts'] == []
        assert result['budget']['calls'] == result['budget']['spent'] == result['budget']['reserved'] == 0
        assert len(children) == 1 and children[0].poll() is not None
