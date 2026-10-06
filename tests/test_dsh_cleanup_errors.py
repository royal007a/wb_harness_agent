"""HA-0092: cleanup faults, local Python child only; no SDK or Provider."""
import json
import os
import signal
import subprocess
from types import SimpleNamespace

import pytest

from adapters import dsh
from adapters.dsh_workspace import cleanup_workspaces
from backend.analysis import Problem
from test_dsh_startup import child_bridge, run_adapter


@pytest.mark.parametrize('code', ['DSH_INITIALIZATION_FAILED', 'DSH_INITIALIZATION_TIMEOUT',
                                 'DSH_RUNTIME_FAILED', 'DSH_CANCELLED'])
def test_signal_permission_does_not_mask_primary_or_skip_cleanup(tmp_path, monkeypatch, code):
    body = json.dumps({'type': 'error', 'code': code})
    children = child_bridge(monkeypatch, f'import sys; sys.stdin.readline(); print({body!r}, flush=True)')
    original = os.killpg
    signals = []
    def denied(pgid, sig):
        if sig:
            signals.append(sig)
            raise PermissionError('SYNTH_CLEANUP_PRIVATE')
        return original(pgid, sig)
    monkeypatch.setattr(os, 'killpg', denied)
    root = tmp_path.resolve() / 'owned'
    with pytest.raises(Problem) as caught:
        run_adapter(root)
    assert caught.value.code == code
    assert signals == [signal.SIGTERM]  # do not escalate after denied signal
    assert children[0].returncode is not None
    assert children[0].stdout.closed
    assert not list(root.glob('run-*'))  # lease was released, not just subprocess reaped


def test_success_with_cleanup_fault_is_not_success(tmp_path, monkeypatch):
    children = child_bridge(monkeypatch,
        'import sys; sys.stdin.readline(); print(\'{"type":"result","finalResponse":"ok"}\', flush=True)')
    original = os.killpg
    def denied(pgid, sig):
        if sig:
            raise PermissionError('SYNTH_CLEANUP_PRIVATE')
        return original(pgid, sig)
    monkeypatch.setattr(os, 'killpg', denied)
    root = tmp_path.resolve() / 'owned'
    with pytest.raises(Problem) as caught:
        run_adapter(root)
    assert caught.value.code == 'DSH_CLEANUP_FAILED'
    assert 'SYNTH_CLEANUP_PRIVATE' not in str(caught.value)
    assert children[0].stdout.closed
    assert not list(root.glob('run-*'))


def test_denied_live_group_keeps_registered_workspace(tmp_path, monkeypatch):
    original_killpg, original_wait = os.killpg, subprocess.Popen.wait
    children = child_bridge(monkeypatch,
        'import sys,time; sys.stdin.readline(); print(\'{"type":"error","code":"DSH_INITIALIZATION_FAILED"}\', flush=True); time.sleep(60)')
    def denied(pgid, sig):
        if sig:
            raise PermissionError('SYNTH_CLEANUP_PRIVATE')
        return original_killpg(pgid, sig)
    monkeypatch.setattr(os, 'killpg', denied)
    root = tmp_path.resolve() / 'owned'
    try:
        with pytest.raises(Problem) as caught:
            run_adapter(root)
        assert caught.value.code == 'DSH_INITIALIZATION_FAILED'
        assert children[0].poll() is None
        assert children[0].stdout.closed
        assert len(list(root.glob('run-*'))) == 1
        assert len(list((root / '.registry').glob('*.json'))) == 1
    finally:
        # Only the actual child created by this test, not a recovered numeric PID.
        if children:
            original_killpg(children[0].pid, signal.SIGKILL)
            original_wait(children[0], timeout=5)
        cleanup_workspaces(root, wait_seconds=0)
    assert not list(root.glob('run-*'))


@pytest.mark.parametrize('phase', ['shutdown', 'server_close', 'join'])
def test_later_resources_close_when_gateway_cleanup_raises(tmp_path, monkeypatch, phase):
    body = json.dumps({'type': 'error', 'code': 'DSH_INITIALIZATION_FAILED'})
    child_bridge(monkeypatch, f'import sys; sys.stdin.readline(); print({body!r}, flush=True)')
    owner = dsh.threading.Thread if phase == 'join' else dsh.ThreadingHTTPServer
    original = getattr(owner, phase)
    calls = []
    def failing(self, *args, **kwargs):
        result = original(self, *args, **kwargs)
        calls.append(phase)
        raise OSError('SYNTH_CLEANUP_PRIVATE')
    monkeypatch.setattr(owner, phase, failing)
    root = tmp_path.resolve() / 'owned'
    with pytest.raises(Problem) as caught:
        run_adapter(root)
    assert caught.value.code == 'DSH_INITIALIZATION_FAILED'
    assert calls
    assert not list(root.glob('run-*'))


@pytest.mark.parametrize('fault', ['wait_os', 'wait_timeout', 'stdin', 'stdout', 'kill'])
def test_process_cleanup_faults_do_not_skip_pipes(monkeypatch, fault):
    calls = []
    def close(name):
        calls.append(name)
        if name == fault:
            raise OSError('SYNTH_CLEANUP_PRIVATE')
    def wait(timeout):
        calls.append('wait')
        if fault == 'wait_os':
            raise OSError('SYNTH_CLEANUP_PRIVATE')
        if fault == 'wait_timeout':
            raise subprocess.TimeoutExpired('synthetic', timeout)
    def killpg(pgid, sig):
        calls.append(sig)
        assert pgid == 987654321  # only a mock, never passed to the operating system
        if fault == 'kill' and sig == signal.SIGKILL:
            raise PermissionError('SYNTH_CLEANUP_PRIVATE')
    monkeypatch.setattr(os, 'killpg', killpg)
    process = SimpleNamespace(pid=987654321, wait=wait,
        stdin=SimpleNamespace(close=lambda: close('stdin')),
        stdout=SimpleNamespace(close=lambda: close('stdout')))
    assert dsh._stop_owned_process(process) is True
    assert calls[-2:] == ['stdin', 'stdout']
