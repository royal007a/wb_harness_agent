"""Reload only the approved gui deployment; preflight before destructive teardown."""
import json
import os
import plistlib
import re
import sqlite3
import subprocess
import sys
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DOMAIN = f'gui/{os.getuid()}'
SERVICE = 'local.harnessagent.workbench'
LABEL = f'{DOMAIN}/{SERVICE}'


class ActivationError(RuntimeError):
    def __init__(self, code, *, action=None, exit_code=None, attempts=0):
        super().__init__(code)
        self.code = code
        self.action = action
        self.exit_code = exit_code
        self.attempts = attempts


def error_record(error):
    record = {'error_type': type(error).__name__}
    if isinstance(error, ActivationError):
        record.update(code=error.code, action=error.action, attempts=error.attempts)
        if error.exit_code is not None:
            record['exit_code'] = error.exit_code
    elif isinstance(error, subprocess.CalledProcessError):
        record['exit_code'] = error.returncode
    return record  # Never serialize arbitrary exception text, stdout or stderr.


def run(*args, timeout=15):
    return subprocess.check_output(args, cwd=ROOT, text=True,
                                   stderr=subprocess.PIPE, timeout=timeout).strip()


def bootstrap(config, timeout_seconds=30):
    """Exit 5 is ambiguous, not an admission to retry indefinitely."""
    if timeout_seconds <= 0:
        raise ActivationError('bootstrap_deadline', action='bootstrap')
    try:
        run('launchctl', 'bootstrap', DOMAIN, str(config), timeout=min(5, timeout_seconds))
    except subprocess.CalledProcessError as exc:
        raise ActivationError('bootstrap_failed', action='bootstrap',
                              exit_code=exc.returncode, attempts=1) from exc
    except subprocess.TimeoutExpired as exc:
        raise ActivationError('command_timeout', action='bootstrap', attempts=1) from exc
    return 1


def command_limit(deadline):
    if deadline is None:
        return 5
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        raise ActivationError('operation_deadline', action='observe')
    return min(5, remaining)


def job_pid(deadline=None):
    """None = absent label, 0 = loaded without a running process."""
    try:
        value = run('launchctl', 'print', LABEL, timeout=command_limit(deadline))
    except subprocess.CalledProcessError as exc:
        if exc.returncode == 113:
            return None
        raise
    found = re.search(r'^\s*pid = ([0-9]+)\s*$', value, re.MULTILINE)
    return int(found.group(1)) if found else 0


def listener_pids(deadline=None):
    try:
        value = run('/usr/sbin/lsof', '-nP', '-iTCP:8765', '-sTCP:LISTEN', '-Fp', timeout=command_limit(deadline))
    except subprocess.CalledProcessError as exc:
        if exc.returncode == 1 and not (exc.output or '').strip() and not (exc.stderr or '').strip():
            return set()
        raise
    return {int(line[1:]) for line in value.splitlines() if re.fullmatch(r'p[0-9]+', line)}


def preflight(configs):
    manager = run('launchctl', 'managername', timeout=5)
    if manager != 'Aqua':
        raise ActivationError('gui_requires_aqua_caller', action='preflight')
    try:
        run('launchctl', 'print', DOMAIN, timeout=5)
    except subprocess.CalledProcessError as exc:
        raise ActivationError('gui_domain_unavailable', action='preflight', exit_code=exc.returncode) from exc
    expected_args = [str(ROOT / '.venv/bin/python'), '-m', 'uvicorn', 'backend.app:app',
                     '--host', '127.0.0.1', '--port', '8765', '--workers', '1', '--no-access-log']
    for config in configs:
        session_types = config.get('LimitLoadToSessionType', ['Aqua'])
        if isinstance(session_types, str):
            session_types = [session_types]
        if (config.get('Label') != SERVICE or config.get('WorkingDirectory') != str(ROOT)
                or config.get('ProgramArguments') != expected_args or 'Aqua' not in session_types
                or config.get('EnvironmentVariables') != {
                    'HARNESS_SANDBOX_BACKEND': 'colima', 'HARNESS_EXTERNAL_SKILLS': 'enabled'}):
            raise ActivationError('plist_not_approved', action='preflight')
    pid, listeners = job_pid(), listener_pids()
    if listeners and (not pid or listeners != {pid}):
        raise ActivationError('port_owned_by_other_process', action='preflight')
    return {'manager': manager, 'domain': DOMAIN, 'previous_pid': pid}


def stop_and_wait(timeout_seconds=15):
    deadline = time.monotonic() + timeout_seconds
    if job_pid(deadline) is not None:
        try:
            run('launchctl', 'bootout', LABEL, timeout=command_limit(deadline))
        except subprocess.CalledProcessError as exc:
            raise ActivationError('bootout_failed', action='bootout', exit_code=exc.returncode, attempts=1) from exc
        except subprocess.TimeoutExpired as exc:
            raise ActivationError('command_timeout', action='bootout', attempts=1) from exc
    while time.monotonic() < deadline:
        if job_pid(deadline) is None and not listener_pids(deadline):
            return
        time.sleep(min(.25, max(0, deadline - time.monotonic())))
    raise ActivationError('teardown_deadline', action='bootout')


def process_identity(deadline=None):
    pid, listeners = job_pid(deadline), listener_pids(deadline)
    if not pid or listeners != {pid}:
        raise OSError('new process has not acquired listener')
    started = run('/bin/ps', '-p', str(pid), '-o', 'lstart=', timeout=command_limit(deadline))
    if not started:
        raise OSError('new process has exited')
    return {'pid': pid, 'started_at': started}


def assert_release(commit, deadline=None):
    if (run('git', 'rev-parse', 'HEAD', timeout=command_limit(deadline)) != commit
            or run('git', 'status', '--porcelain', timeout=command_limit(deadline))):
        raise ActivationError('release_changed_during_activation', action='health')


def healthy(expected_image, expected_commit, timeout_seconds=60):
    deadline = time.monotonic() + timeout_seconds
    paths = {'health': '/api/v1/health', 'agent_runtime': '/api/local/agent-runtime/runtime',
             'skills': '/api/local/external-skills/runtime'}
    identity = None
    while time.monotonic() < deadline:
        try:
            assert_release(expected_commit, deadline)
            before = process_identity(deadline)
            if identity is not None and before != identity:
                raise ActivationError('process_identity_changed', action='health')
            identity = before
            result = {}
            for key, path in paths.items():
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise OSError('health deadline exhausted')
                with urllib.request.urlopen('http://127.0.0.1:8765' + path,
                                            timeout=min(20, remaining)) as response:
                    result[key] = json.load(response)
            if result['health'].get('status') != 'ok':
                raise OSError('service is not healthy yet')
            if (result['health'].get('model_calls_enabled') is not False or
                    result['agent_runtime'].get('runtime_enabled') is not False or
                    result['agent_runtime'].get('tool_binding_count') != 0):
                raise ActivationError('unexpected_model_tool_gate', action='health')
            skill = result['skills']
            if skill.get('runtime_enabled') is not True or skill.get('backend') != 'colima':
                raise ActivationError('unexpected_skill_profile', action='health')
            if skill.get('blockers') != []:
                raise OSError('external Skill is not ready yet')
            if skill.get('image_id') != expected_image:
                raise ActivationError('unexpected_skill_image', action='health')
            assert_release(expected_commit, deadline)
            if process_identity(deadline) != identity:
                raise ActivationError('process_identity_changed', action='health')
            result['process'] = identity
            return result
        except (OSError, ValueError):
            time.sleep(min(1, max(0, deadline - time.monotonic())))
    raise ActivationError('deployment health deadline exhausted', action='health')


def main():
    previous = sys.argv[1]
    assert re.fullmatch('[a-f0-9]{40}', previous)
    work_item = sys.argv[2] if len(sys.argv) > 2 else 'ha0052'
    assert work_item in {'ha0052', 'ha0054', 'ha0055', 'ha0056'}
    commit = run('git', 'rev-parse', 'HEAD')
    assert not run('git', 'status', '--porcelain')
    config = ROOT / 'deploy/local.macos.plist'
    desired = plistlib.loads(config.read_bytes())
    old = run('git', 'show', previous + ':deploy/local.macos.plist')
    prior = plistlib.loads(old.encode())
    # No stop, backup or bootstrap occurs until both configurations are usable.
    topology = preflight([desired, prior])
    run('plutil', '-lint', str(config))
    image = run('/opt/homebrew/bin/docker', '--context', 'colima', 'image', 'inspect',
                'harnessagent-external-skill:0.1', '--format', '{{.Id}}')
    assert image.startswith('sha256:')
    backup = ROOT / '.local/backups' / (work_item + '-' + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ'))
    backup.mkdir(parents=True, mode=0o700)
    (backup / 'previous.plist').write_text(old)
    db = ROOT / '.local/harness.db'
    with sqlite3.connect('file:' + str(db) + '?mode=ro', uri=True) as source:
        with sqlite3.connect(backup / 'harness.db') as target:
            source.backup(target)
            assert target.execute('PRAGMA integrity_check').fetchone()[0] == 'ok'
    (backup / 'harness.db').chmod(0o600)
    phase = 'bootout'
    try:
        stop_and_wait()
        phase = 'bootstrap'
        attempts = bootstrap(config)
        phase = 'health'
        status = healthy(image, commit)
    except (Exception, KeyboardInterrupt) as activation_error:
        recovery = {'scope': 'previous_plist_only', 'healthy': False, 'phase': 'not_attempted',
                    'code_commit': commit, 'config_source_commit': previous,
                    'code_rollback': False, 'database_rollback': False}
        if not isinstance(activation_error, KeyboardInterrupt):
            try:
                recovery['phase'] = 'preflight'
                preflight([prior])
                recovery['phase'] = 'bootout'
                stop_and_wait()
                recovery['phase'] = 'bootstrap'
                recovery['bootstrap_attempts'] = bootstrap(backup / 'previous.plist')
                recovery['phase'] = 'health'
                recovery['health'] = healthy(image, commit)
                recovery['healthy'] = True
                recovery['phase'] = 'verified'
            except (Exception, KeyboardInterrupt) as recovery_error:
                recovery.update(error_record(recovery_error))
        failure = {'commit': commit, 'backup': str(backup), 'activation_succeeded': False,
                   'phase': phase, 'recovery': recovery, **error_record(activation_error)}
        (backup / 'activation-failure.json').write_text(json.dumps(failure, indent=2) + '\n')
        (backup / 'activation-failure.json').chmod(0o600)
        if isinstance(activation_error, KeyboardInterrupt):
            raise
        raise RuntimeError('Activation failed; previous plist recovery healthy=' +
                           str(recovery['healthy']) + '; see activation-failure.json') from activation_error
    result = dict(commit=commit, backup=str(backup), database=str(db), runtime=status['skills'],
                  health=status['health'], agent_runtime=status['agent_runtime'], bootstrap_attempts=attempts,
                  topology=topology, process=status['process'], code_rollback=False, database_rollback=False)
    (backup / 'deployment.json').write_text(json.dumps(result, indent=2) + '\n')
    (backup / 'deployment.json').chmod(0o600)
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
