"""Fault injection only: no real launchctl, network or user database access."""
import json
import io
import plistlib
import sqlite3
import subprocess

import pytest

from deploy import activate_local_skills as activation


COMMIT = 'a' * 40
PREVIOUS = 'b' * 40
IMAGE = 'sha256:' + 'c' * 64
SETTINGS = {'EnvironmentVariables': {'HARNESS_SANDBOX_BACKEND': 'colima', 'HARNESS_EXTERNAL_SKILLS': 'enabled'}}


@pytest.fixture
def deployment(tmp_path, monkeypatch):
    (tmp_path / 'deploy').mkdir()
    (tmp_path / 'deploy/local.macos.plist').write_bytes(plistlib.dumps(SETTINGS))
    (tmp_path / '.local').mkdir()
    with sqlite3.connect(tmp_path / '.local/harness.db') as db:
        db.execute('CREATE TABLE sample(value)')
        db.execute("INSERT INTO sample VALUES('retained')")
    monkeypatch.setattr(activation, 'ROOT', tmp_path)
    monkeypatch.setattr(activation.sys, 'argv', ['activate', PREVIOUS, 'ha0055'])
    monkeypatch.setattr(activation.time, 'sleep', lambda _: None)
    calls, answers = [], []

    def command(*args, **kwargs):
        calls.append(args)
        if args[:3] == ('git', 'rev-parse', 'HEAD'):
            return COMMIT
        if args[:2] == ('git', 'show'):
            return plistlib.dumps(SETTINGS).decode()
        if 'image' in args:
            return IMAGE
        if args[:2] == ('launchctl', 'bootstrap') and answers:
            response = answers.pop(0)
            if response:
                raise subprocess.CalledProcessError(response, args)
        return ''

    class Response:
        def __init__(self, url):
            if url.endswith('/api/v1/health'):
                self.value = {'status': 'ok', 'model_calls_enabled': False}
            elif url.endswith('/agent-runtime/runtime'):
                self.value = {'runtime_enabled': False, 'tool_binding_count': 0}
            else:
                self.value = {'runtime_enabled': True, 'blockers': [], 'backend': 'colima', 'image_id': IMAGE}

        def __enter__(self):
            return self

        def __exit__(self, *_):
            pass

        def read(self):
            return json.dumps(self.value).encode()

    monkeypatch.setattr(activation, 'run', command)
    monkeypatch.setattr(activation.subprocess, 'run', lambda *a, **kw: subprocess.CompletedProcess(a, 0))
    monkeypatch.setattr(activation.urllib.request, 'urlopen', lambda url, **kw: Response(url))
    return tmp_path, calls, answers


def test_transient_bootstrap_failure_retries_same_config_without_rollback(deployment):
    root, calls, answers = deployment
    answers.extend([5, 5, 0])
    activation.main()
    starts = [c for c in calls if c[:2] == ('launchctl', 'bootstrap')]
    assert len(starts) == 3
    assert {c[-1] for c in starts} == {str(root / 'deploy/local.macos.plist')}
    receipts = list(root.glob('.local/backups/*/deployment.json'))
    assert len(receipts) == 1 and json.loads(receipts[0].read_text())['commit'] == COMMIT
    assert not list(root.glob('.local/backups/*/activation-failure.json'))


def test_failed_activation_records_verified_plist_recovery(deployment):
    root, calls, answers = deployment
    answers.extend([78, 0])
    with pytest.raises(Exception):
        activation.main()
    receipts = list(root.glob('.local/backups/*/activation-failure.json'))
    assert len(receipts) == 1
    record = json.loads(receipts[0].read_text())
    assert record['activation_succeeded'] is False
    assert record['phase'] == 'bootstrap' and record['exit_code'] == 78
    assert record['recovery']['healthy'] is True
    assert record['recovery']['phase'] == 'verified'
    assert record['recovery']['scope'] == 'previous_plist_only'
    assert not list(root.glob('.local/backups/*/deployment.json'))
    with sqlite3.connect(root / '.local/harness.db') as db:
        assert db.execute('SELECT value FROM sample').fetchone()[0] == 'retained'


def test_bootstrap_permanent_five_shares_deadline_with_command_time(monkeypatch):
    clock, calls = [0.0], []
    monkeypatch.setattr(activation.time, 'monotonic', lambda: clock[0])
    monkeypatch.setattr(activation.time, 'sleep', lambda seconds: clock.__setitem__(0, clock[0] + seconds))

    def command(*args, timeout):
        calls.append(timeout)
        clock[0] += min(2, timeout)
        raise subprocess.CalledProcessError(5, args)

    monkeypatch.setattr(activation, 'run', command)
    with pytest.raises(RuntimeError, match='retry deadline exhausted'):
        activation.bootstrap('/synthetic.plist', timeout_seconds=3)
    assert calls == [3] and clock[0] == 3


@pytest.mark.parametrize('exit_code', [1, 78])
def test_bootstrap_does_not_retry_other_errors(monkeypatch, exit_code):
    calls = []

    def command(*args, **kwargs):
        calls.append(args)
        raise subprocess.CalledProcessError(exit_code, args)

    monkeypatch.setattr(activation, 'run', command)
    with pytest.raises(subprocess.CalledProcessError) as failure:
        activation.bootstrap('/synthetic.plist')
    assert failure.value.returncode == exit_code and len(calls) == 1


def test_bootstrap_command_timeout_is_not_blindly_retried(monkeypatch):
    calls = []

    def command(*args, timeout):
        calls.append(timeout)
        raise subprocess.TimeoutExpired(args, timeout)

    monkeypatch.setattr(activation, 'run', command)
    with pytest.raises(subprocess.TimeoutExpired):
        activation.bootstrap('/synthetic.plist')
    assert len(calls) == 1 and 0 < calls[0] <= 5


def test_health_failure_then_recovery_failure_never_records_success(deployment, monkeypatch):
    root, calls, _ = deployment
    checks = []

    def unhealthy(*args):
        checks.append(args)
        raise RuntimeError('synthetic health failure')

    monkeypatch.setattr(activation, 'healthy', unhealthy)
    with pytest.raises(RuntimeError, match='recovery healthy=False'):
        activation.main()
    assert len(checks) == 2
    receipt = next(root.glob('.local/backups/*/activation-failure.json'))
    result = json.loads(receipt.read_text())
    assert result['phase'] == 'health'
    assert result['recovery']['healthy'] is False and result['recovery']['phase'] == 'health'
    assert not list(root.glob('.local/backups/*/deployment.json'))


def test_recovery_bootstrap_failure_is_recorded(deployment):
    root, _, answers = deployment
    answers.extend([78, 78])
    with pytest.raises(RuntimeError, match='recovery healthy=False'):
        activation.main()
    receipt = json.loads(next(root.glob('.local/backups/*/activation-failure.json')).read_text())
    assert receipt['recovery']['error_type'] == 'CalledProcessError'
    assert receipt['recovery']['healthy'] is False


@pytest.mark.parametrize('kind', ['model_enabled', 'tools_enabled', 'image_drift', 'backend_drift'])
def test_health_rejects_gate_and_image_drift(deployment, monkeypatch, kind):
    original = activation.urllib.request.urlopen

    def altered(url, **kwargs):
        with original(url, **kwargs) as response:
            value = json.load(response)
        if kind == 'model_enabled' and url.endswith('/agent-runtime/runtime'):
            value['runtime_enabled'] = True
        if kind == 'tools_enabled' and url.endswith('/agent-runtime/runtime'):
            value['tool_binding_count'] = 1
        if kind == 'image_drift' and url.endswith('/external-skills/runtime'):
            value['image_id'] = 'sha256:' + 'd' * 64
        if kind == 'backend_drift' and url.endswith('/external-skills/runtime'):
            value['backend'] = 'linux-docker'
        return io.BytesIO(json.dumps(value).encode())

    monkeypatch.setattr(activation.urllib.request, 'urlopen', altered)
    with pytest.raises(RuntimeError, match='unexpected'):
        activation.healthy(IMAGE)


def test_health_wait_is_bounded(monkeypatch):
    clock, calls = [0.0], []
    monkeypatch.setattr(activation.time, 'monotonic', lambda: clock[0])
    monkeypatch.setattr(activation.time, 'sleep', lambda seconds: clock.__setitem__(0, clock[0] + seconds))

    def unavailable(url, timeout):
        calls.append(timeout)
        clock[0] += timeout
        raise OSError('synthetic transport unavailable')

    monkeypatch.setattr(activation.urllib.request, 'urlopen', unavailable)
    with pytest.raises(RuntimeError, match='health deadline exhausted'):
        activation.healthy(IMAGE, timeout_seconds=2)
    assert clock[0] == 2 and calls == [2]


def test_temporary_sandbox_unavailability_retries_before_image_check(deployment, monkeypatch):
    original = activation.urllib.request.urlopen
    skill_checks = []

    def starting(url, **kwargs):
        with original(url, **kwargs) as response:
            value = json.load(response)
        if url.endswith('/external-skills/runtime'):
            skill_checks.append(url)
            if len(skill_checks) == 1:
                value.update(image_id=None, blockers=['sandbox_unavailable'])
        return io.BytesIO(json.dumps(value).encode())

    monkeypatch.setattr(activation.urllib.request, 'urlopen', starting)
    assert activation.healthy(IMAGE)['skills']['image_id'] == IMAGE
    assert len(skill_checks) == 2


def test_dirty_worktree_stops_before_service_or_backup_mutation(deployment, monkeypatch):
    root, calls, _ = deployment
    original = activation.run

    def dirty(*args, **kwargs):
        if args == ('git', 'status', '--porcelain'):
            return ' M implementation.py'
        return original(*args, **kwargs)

    monkeypatch.setattr(activation, 'run', dirty)
    with pytest.raises(AssertionError):
        activation.main()
    assert not any(c[0] == 'launchctl' for c in calls)
    assert not (root / '.local/backups').exists()


def test_bootout_timeout_records_uncertain_stop_and_checks_recovery(deployment, monkeypatch):
    root, _, _ = deployment
    original = activation.run

    def command(*args, **kwargs):
        if args[:2] == ('launchctl', 'bootout'):
            raise subprocess.TimeoutExpired(args, 15)
        return original(*args, **kwargs)

    monkeypatch.setattr(activation, 'run', command)
    with pytest.raises(RuntimeError, match='recovery healthy=True'):
        activation.main()
    receipt = json.loads(next(root.glob('.local/backups/*/activation-failure.json')).read_text())
    assert receipt['phase'] == 'bootout'
    assert receipt['error_type'] == 'TimeoutExpired'
    assert receipt['recovery']['phase'] == 'verified'
    assert not list(root.glob('.local/backups/*/deployment.json'))
