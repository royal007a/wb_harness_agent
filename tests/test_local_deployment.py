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
def settings(root):
    return {'Label': activation.SERVICE, 'WorkingDirectory': str(root),
            'ProgramArguments': [str(root / '.venv/bin/python'), '-m', 'uvicorn', 'backend.app:app',
                                 '--host', '127.0.0.1', '--port', '8765', '--workers', '1', '--no-access-log'],
            'EnvironmentVariables': {'HARNESS_SANDBOX_BACKEND': 'colima', 'HARNESS_EXTERNAL_SKILLS': 'enabled'}}


@pytest.fixture
def deployment(tmp_path, monkeypatch):
    (tmp_path / 'deploy').mkdir()
    (tmp_path / 'deploy/local.macos.plist').write_bytes(plistlib.dumps(settings(tmp_path)))
    (tmp_path / '.local').mkdir()
    with sqlite3.connect(tmp_path / '.local/harness.db') as db:
        db.execute('CREATE TABLE sample(value)')
        db.execute("INSERT INTO sample VALUES('retained')")
    monkeypatch.setattr(activation, 'ROOT', tmp_path)
    monkeypatch.setattr(activation.sys, 'argv', ['activate', PREVIOUS, 'ha0055'])
    monkeypatch.setattr(activation.time, 'sleep', lambda _: None)
    calls, answers = [], []
    process = {'pid': 100, 'generation': 0}

    def command(*args, **kwargs):
        calls.append(args)
        if args[:3] == ('git', 'rev-parse', 'HEAD'):
            return COMMIT
        if args[:2] == ('git', 'show'):
            return plistlib.dumps(settings(tmp_path)).decode()
        if 'image' in args:
            return IMAGE
        if args == ('launchctl', 'managername'):
            return 'Aqua'
        if args == ('launchctl', 'print', activation.LABEL):
            if process['pid'] is None:
                raise subprocess.CalledProcessError(113, args, output='', stderr='')
            return f"pid = {process['pid']}\n"
        if args[0] == '/usr/sbin/lsof':
            return f"p{process['pid']}\n" if process['pid'] else ''
        if args[0] == '/bin/ps':
            return f"synthetic-start-{process['generation']}"
        if args[:2] == ('launchctl', 'bootout'):
            process['pid'] = None
        if args[:2] == ('launchctl', 'bootstrap'):
            response = answers.pop(0) if answers else 0
            if response:
                raise subprocess.CalledProcessError(response, args, output='synthetic-secret', stderr='synthetic-secret')
            process['generation'] += 1
            process['pid'] = 100 + process['generation']
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


def test_success_binds_new_process_and_release_without_rollback(deployment):
    root, calls, answers = deployment
    activation.main()
    starts = [c for c in calls if c[:2] == ('launchctl', 'bootstrap')]
    assert len(starts) == 1
    assert {c[-1] for c in starts} == {str(root / 'deploy/local.macos.plist')}
    receipts = list(root.glob('.local/backups/*/deployment.json'))
    assert len(receipts) == 1 and json.loads(receipts[0].read_text())['commit'] == COMMIT
    assert json.loads(receipts[0].read_text())['process']['pid'] == 101
    assert json.loads(receipts[0].read_text())['bootstrap_attempts'] == 1
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


def test_bootstrap_five_is_reported_without_blind_retries(monkeypatch):
    clock, calls = [0.0], []
    monkeypatch.setattr(activation.time, 'monotonic', lambda: clock[0])
    monkeypatch.setattr(activation.time, 'sleep', lambda seconds: clock.__setitem__(0, clock[0] + seconds))

    def command(*args, timeout):
        calls.append(timeout)
        clock[0] += min(2, timeout)
        raise subprocess.CalledProcessError(5, args)

    monkeypatch.setattr(activation, 'run', command)
    with pytest.raises(activation.ActivationError) as failure:
        activation.bootstrap('/synthetic.plist', timeout_seconds=3)
    assert calls == [3] and clock[0] == 2
    assert failure.value.exit_code == 5 and failure.value.attempts == 1


@pytest.mark.parametrize('exit_code', [1, 78])
def test_bootstrap_does_not_retry_other_errors(monkeypatch, exit_code):
    calls = []

    def command(*args, **kwargs):
        calls.append(args)
        raise subprocess.CalledProcessError(exit_code, args)

    monkeypatch.setattr(activation, 'run', command)
    with pytest.raises(activation.ActivationError) as failure:
        activation.bootstrap('/synthetic.plist')
    assert failure.value.exit_code == exit_code and len(calls) == 1


def test_bootstrap_command_timeout_is_not_blindly_retried(monkeypatch):
    calls = []

    def command(*args, timeout):
        calls.append(timeout)
        raise subprocess.TimeoutExpired(args, timeout)

    monkeypatch.setattr(activation, 'run', command)
    with pytest.raises(activation.ActivationError, match='command_timeout'):
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
    assert receipt['recovery']['error_type'] == 'ActivationError'
    assert receipt['recovery']['exit_code'] == 78
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
        activation.healthy(IMAGE, COMMIT)


def test_health_wait_is_bounded(monkeypatch):
    clock, calls = [0.0], []
    monkeypatch.setattr(activation.time, 'monotonic', lambda: clock[0])
    monkeypatch.setattr(activation.time, 'sleep', lambda seconds: clock.__setitem__(0, clock[0] + seconds))
    monkeypatch.setattr(activation, 'assert_release', lambda *a: None)
    monkeypatch.setattr(activation, 'process_identity', lambda *a: {'pid': 101})

    def unavailable(url, timeout):
        calls.append(timeout)
        clock[0] += timeout
        raise OSError('synthetic transport unavailable')

    monkeypatch.setattr(activation.urllib.request, 'urlopen', unavailable)
    with pytest.raises(RuntimeError, match='health deadline exhausted'):
        activation.healthy(IMAGE, COMMIT, timeout_seconds=2)
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
    assert activation.healthy(IMAGE, COMMIT)['skills']['image_id'] == IMAGE
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


def test_recovery_bootout_timeout_is_not_ignored(deployment, monkeypatch):
    root, _, _ = deployment
    original = activation.run

    def command(*args, **kwargs):
        if args[:2] == ('launchctl', 'bootout'):
            raise subprocess.TimeoutExpired(args, 15)
        return original(*args, **kwargs)

    monkeypatch.setattr(activation, 'run', command)
    with pytest.raises(RuntimeError, match='recovery healthy=False'):
        activation.main()
    receipt = json.loads(next(root.glob('.local/backups/*/activation-failure.json')).read_text())
    assert receipt['phase'] == 'bootout'
    assert receipt['error_type'] == 'ActivationError'
    assert receipt['code'] == 'command_timeout'
    assert receipt['recovery']['phase'] == 'bootout'
    assert receipt['recovery']['code'] == 'command_timeout'
    assert not list(root.glob('.local/backups/*/deployment.json'))


@pytest.mark.parametrize('kind', ['background', 'domain', 'session_type', 'foreign_port'])
def test_preflight_failure_never_stops_or_starts_service(deployment, monkeypatch, kind):
    root, calls, _ = deployment
    original = activation.run
    def command(*args, **kwargs):
        if kind == 'background' and args == ('launchctl', 'managername'):
            return 'Background'
        if kind == 'domain' and args == ('launchctl', 'print', activation.DOMAIN):
            raise subprocess.CalledProcessError(125, args)
        if kind == 'foreign_port' and args[0] == '/usr/sbin/lsof':
            return 'p999\n'
        return original(*args, **kwargs)
    monkeypatch.setattr(activation, 'run', command)
    if kind == 'session_type':
        config = settings(root)
        config['LimitLoadToSessionType'] = ['Background']
        (root / 'deploy/local.macos.plist').write_bytes(plistlib.dumps(config))
    with pytest.raises(activation.ActivationError):
        activation.main()
    assert not any(c[:2] in [('launchctl', 'bootout'), ('launchctl', 'bootstrap')] for c in calls)
    assert not (root / '.local/backups').exists()


def test_port_must_be_free_before_bootstrap(deployment, monkeypatch):
    _, calls, _ = deployment
    original = activation.listener_pids
    checks = []
    def listeners(*args):
        if any(c[:2] == ('launchctl', 'bootout') for c in calls) and not any(c[:2] == ('launchctl', 'bootstrap') for c in calls):
            checks.append(1)
            if len(checks) < 3:
                return {100}
        return original(*args)
    monkeypatch.setattr(activation, 'listener_pids', listeners)
    activation.main()
    assert len(checks) == 3


def test_teardown_deadline_does_not_kill_foreign_listener(monkeypatch):
    clock = [0.0]
    monkeypatch.setattr(activation.time, 'monotonic', lambda: clock[0])
    monkeypatch.setattr(activation.time, 'sleep', lambda n: clock.__setitem__(0, clock[0] + n))
    monkeypatch.setattr(activation, 'job_pid', lambda *a: None)
    monkeypatch.setattr(activation, 'listener_pids', lambda *a: {999})
    with pytest.raises(activation.ActivationError, match='teardown_deadline'):
        activation.stop_and_wait(.7)
    assert clock[0] == .7


@pytest.mark.parametrize('kind', ['pid', 'start_time', 'commit', 'dirty'])
def test_health_rejects_identity_or_release_drift(deployment, monkeypatch, kind):
    original = activation.process_identity
    checks = []
    def identity(*args):
        result = original(*args)
        checks.append(1)
        if len(checks) > 1:
            if kind == 'pid':
                result['pid'] += 1
            if kind == 'start_time':
                result['started_at'] = 'changed'
        return result
    monkeypatch.setattr(activation, 'process_identity', identity)
    original_run = activation.run
    def command(*args, **kwargs):
        if checks and kind == 'commit' and args == ('git', 'rev-parse', 'HEAD'):
            return 'd' * 40
        if checks and kind == 'dirty' and args == ('git', 'status', '--porcelain'):
            return ' M source.py'
        return original_run(*args, **kwargs)
    monkeypatch.setattr(activation, 'run', command)
    with pytest.raises(activation.ActivationError):
        activation.healthy(IMAGE, COMMIT)


def test_old_listener_is_not_accepted_as_new_launchd_pid(deployment, monkeypatch):
    monkeypatch.setattr(activation, 'job_pid', lambda *a: 101)
    monkeypatch.setattr(activation, 'listener_pids', lambda *a: {100})
    with pytest.raises(OSError, match='new process has not acquired listener'):
        activation.process_identity()


def test_interrupt_after_bootout_writes_failure_without_more_activation(deployment, monkeypatch):
    root, calls, _ = deployment
    monkeypatch.setattr(activation, 'bootstrap', lambda *a: (_ for _ in ()).throw(KeyboardInterrupt()))
    with pytest.raises(KeyboardInterrupt):
        activation.main()
    receipt = json.loads(next(root.glob('.local/backups/*/activation-failure.json')).read_text())
    assert receipt['error_type'] == 'KeyboardInterrupt'
    assert receipt['recovery']['phase'] == 'not_attempted'
    assert not receipt['recovery']['healthy']
    assert len([c for c in calls if c[:2] == ('launchctl', 'bootout')]) == 1
    assert not list(root.glob('.local/backups/*/deployment.json'))


def test_five_and_recovery_receipt_preserve_cause_without_secrets(deployment):
    root, calls, answers = deployment
    answers.extend([5, 0])
    with pytest.raises(RuntimeError):
        activation.main()
    raw = next(root.glob('.local/backups/*/activation-failure.json')).read_text()
    receipt = json.loads(raw)
    assert receipt['exit_code'] == 5 and receipt['attempts'] == 1
    assert receipt['recovery']['healthy'] is True
    assert receipt['recovery']['code_commit'] == COMMIT
    assert receipt['recovery']['config_source_commit'] == PREVIOUS
    assert receipt['recovery']['code_rollback'] is False
    assert receipt['recovery']['database_rollback'] is False
    assert 'synthetic-secret' not in raw
    assert len([c for c in calls if c[:2] == ('launchctl', 'bootstrap')]) == 2


@pytest.fixture
def delayed_exit(deployment, monkeypatch):
    root, calls, _ = deployment
    clock = [0.0]
    exit_at = [20.0]
    listener_kind = ['owned']
    original = activation.run
    monkeypatch.setattr(activation.time, 'monotonic', lambda: clock[0])
    monkeypatch.setattr(activation.time, 'sleep', lambda n: clock.__setitem__(0, clock[0] + n))

    def command(*args, **kwargs):
        stopped = any(c[:2] == ('launchctl', 'bootout') for c in calls)
        started = any(c[:2] == ('launchctl', 'bootstrap') for c in calls)
        if stopped and not started:
            if args[0] == '/usr/sbin/lsof' and clock[0] < exit_at[0]:
                return 'p100\np999' if listener_kind[0] == 'multiple' else 'p100'
            if args[0] == '/bin/ps' and listener_kind[0] == 'reused':
                return 'different-process-with-reused-pid'
        if args[:2] == ('launchctl', 'bootstrap'):
            assert clock[0] >= exit_at[0], 'bootstrap before previous listener released'
        return original(*args, **kwargs)

    monkeypatch.setattr(activation, 'run', command)
    return root, calls, clock, exit_at, listener_kind


def test_twenty_second_graceful_exit_does_not_strand_service(delayed_exit):
    root, calls, clock, _, _ = delayed_exit
    activation.main()
    assert clock[0] == 20
    assert len([c for c in calls if c[:2] == ('launchctl', 'bootout')]) == 1
    assert len([c for c in calls if c[:2] == ('launchctl', 'bootstrap')]) == 1
    assert len(list(root.glob('.local/backups/*/deployment.json'))) == 1


def test_recovery_waits_for_known_orphan_before_bootstrap(delayed_exit):
    root, calls, clock, exit_at, _ = delayed_exit
    exit_at[0] = 50
    with pytest.raises(RuntimeError, match='recovery healthy=True'):
        activation.main()
    receipt = json.loads(next(root.glob('.local/backups/*/activation-failure.json')).read_text())
    assert receipt['code'] == 'teardown_deadline'
    assert receipt['recovery']['healthy'] is True
    assert receipt['teardown']['last_label_pid'] is None
    assert receipt['teardown']['last_listener_pids'] == [100]
    assert receipt['teardown']['bootout_attempted'] is True
    assert receipt['teardown']['bootout_returned'] is True
    assert receipt['teardown']['service_stopped'] is False
    assert receipt['recovery']['teardown']['bootout_attempted'] is False
    assert receipt['recovery']['teardown']['service_stopped'] is True
    assert clock[0] == 50
    assert len([c for c in calls if c[:2] == ('launchctl', 'bootout')]) == 1
    assert len([c for c in calls if c[:2] == ('launchctl', 'bootstrap')]) == 1
    assert not list(root.glob('.local/backups/*/deployment.json'))


@pytest.mark.parametrize('kind', ['reused', 'multiple'])
def test_recovery_does_not_trust_pid_alone_or_multiple_listeners(delayed_exit, kind):
    root, calls, _, exit_at, listener_kind = delayed_exit
    exit_at[0], listener_kind[0] = 50, kind
    with pytest.raises(RuntimeError, match='recovery healthy=False'):
        activation.main()
    receipt = json.loads(next(root.glob('.local/backups/*/activation-failure.json')).read_text())
    assert receipt['recovery']['code'] == 'port_owned_by_other_process'
    assert not any(c[:2] == ('launchctl', 'bootstrap') for c in calls)


def test_known_orphan_wait_has_a_second_hard_deadline(delayed_exit):
    root, calls, clock, exit_at, _ = delayed_exit
    exit_at[0] = 1000
    with pytest.raises(RuntimeError, match='recovery healthy=False'):
        activation.main()
    receipt = json.loads(next(root.glob('.local/backups/*/activation-failure.json')).read_text())
    assert receipt['recovery']['code'] == 'teardown_deadline'
    assert clock[0] == 90
    assert not any(c[:2] == ('launchctl', 'bootstrap') for c in calls)


@pytest.mark.parametrize('observe', ['label', 'listener'])
def test_teardown_observation_timeout_preserves_deadline_cause(monkeypatch, observe):
    clock = [0.0]
    monkeypatch.setattr(activation.time, 'monotonic', lambda: clock[0])
    monkeypatch.setattr(activation.time, 'sleep', lambda n: clock.__setitem__(0, clock[0] + n))
    def command(*args, timeout):
        if (observe == 'label' and args[:2] == ('launchctl', 'print')) or (
                observe == 'listener' and args[0] == '/usr/sbin/lsof'):
            clock[0] += timeout
            raise subprocess.TimeoutExpired(args, timeout)
        if args[:2] == ('launchctl', 'print'):
            raise subprocess.CalledProcessError(113, args)
        return ''
    monkeypatch.setattr(activation, 'run', command)
    with pytest.raises(activation.ActivationError, match='teardown_deadline'):
        activation.stop_and_wait(.1)
    assert clock[0] == .1


def test_recovery_keyboard_interrupt_is_reraised_after_receipt(deployment, monkeypatch):
    root, _, answers = deployment
    answers.append(78)
    def interrupted(*args):
        raise KeyboardInterrupt()
    monkeypatch.setattr(activation, 'healthy', interrupted)
    with pytest.raises(KeyboardInterrupt):
        activation.main()
    receipt = json.loads(next(root.glob('.local/backups/*/activation-failure.json')).read_text())
    assert receipt['recovery']['error_type'] == 'KeyboardInterrupt'
    assert receipt['recovery']['healthy'] is False
    assert not list(root.glob('.local/backups/*/deployment.json'))


@pytest.mark.parametrize('key,value', [('Program', '/unapproved/program'), ('ExitTimeOut', 0),
                                      ('ExitTimeOut', 60), ('ExitTimeOut', True)])
def test_plist_execution_override_is_rejected_before_stop(deployment, key, value):
    root, calls, _ = deployment
    config = settings(root)
    config[key] = value
    (root / 'deploy/local.macos.plist').write_bytes(plistlib.dumps(config))
    with pytest.raises(activation.ActivationError, match='plist_not_approved'):
        activation.main()
    assert not any(c[:2] in [('launchctl', 'bootstrap'), ('launchctl', 'bootout')] for c in calls)


def test_synchronous_bootout_gets_exit_window_within_total_deadline(deployment, monkeypatch):
    root, _, _ = deployment
    clock, limits = [0.0], []
    original = activation.run
    monkeypatch.setattr(activation.time, 'monotonic', lambda: clock[0])
    monkeypatch.setattr(activation.time, 'sleep', lambda n: clock.__setitem__(0, clock[0] + n))
    def command(*args, **kwargs):
        if args[:2] == ('launchctl', 'bootout'):
            limits.append(kwargs['timeout'])
            assert kwargs['timeout'] > 20
            clock[0] += 20
        return original(*args, **kwargs)
    monkeypatch.setattr(activation, 'run', command)
    activation.main()
    receipt = json.loads(next(root.glob('.local/backups/*/deployment.json')).read_text())
    assert limits == [30] and clock[0] == 20
    assert receipt['teardown']['service_stopped'] is True


def test_early_observer_timeout_is_not_misreported_as_deadline(monkeypatch):
    monkeypatch.setattr(activation.time, 'monotonic', lambda: 0)
    def command(*args, **kwargs):
        raise subprocess.TimeoutExpired(args, 5)
    monkeypatch.setattr(activation, 'run', command)
    with pytest.raises(activation.ActivationError, match='command_timeout') as error:
        activation.stop_and_wait(45)
    assert error.value.action == 'observe' and error.value.attempts == 0


def test_vanished_ps_is_retried_without_accepting_a_different_identity(deployment, monkeypatch):
    original = activation.run
    observations = []
    def command(*args, **kwargs):
        if args[0] == '/bin/ps':
            observations.append(1)
            if len(observations) == 1:
                raise subprocess.CalledProcessError(1, args)
        return original(*args, **kwargs)
    monkeypatch.setattr(activation, 'run', command)
    assert activation.healthy(IMAGE, COMMIT)['process']['pid'] == 100
    assert len(observations) == 3


def test_known_orphan_exiting_between_lsof_and_ps_can_recover(delayed_exit, monkeypatch):
    root, calls, clock, exit_at, _ = delayed_exit
    exit_at[0] = 50
    original = activation.run
    def command(*args, **kwargs):
        if args[0] == '/bin/ps' and clock[0] == 45:
            clock[0] = 50
            raise subprocess.CalledProcessError(1, args)
        return original(*args, **kwargs)
    monkeypatch.setattr(activation, 'run', command)
    with pytest.raises(RuntimeError, match='recovery healthy=True'):
        activation.main()
    receipt = json.loads(next(root.glob('.local/backups/*/activation-failure.json')).read_text())
    assert receipt['recovery']['healthy'] is True
    assert len([c for c in calls if c[:2] == ('launchctl', 'bootstrap')]) == 1
