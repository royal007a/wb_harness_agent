"""HA-0052: reload the approved local launchd deployment with DB/config backup."""
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
LABEL = f'gui/{os.getuid()}/local.harnessagent.workbench'


def run(*args, timeout=15):
    return subprocess.check_output(args, cwd=ROOT, text=True,
                                   stderr=subprocess.PIPE, timeout=timeout).strip()


def bootstrap(config, timeout_seconds=30):
    """Only exit 5 is retryable; command time and sleeps share one deadline."""
    deadline = time.monotonic() + timeout_seconds
    attempts = 0
    while True:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise RuntimeError('launchd bootstrap retry deadline exhausted')
        attempts += 1
        try:
            run('launchctl', 'bootstrap', f'gui/{os.getuid()}', str(config),
                timeout=min(5, remaining))
            return attempts
        except subprocess.CalledProcessError as exc:
            if exc.returncode != 5:
                raise
            # launchd can retain teardown state after bootout has returned.
            time.sleep(min(1, max(0, deadline - time.monotonic())))


def healthy(expected_image, timeout_seconds=60):
    deadline = time.monotonic() + timeout_seconds
    paths = {'health': '/api/v1/health', 'agent_runtime': '/api/local/agent-runtime/runtime',
             'skills': '/api/local/external-skills/runtime'}
    while time.monotonic() < deadline:
        try:
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
                raise RuntimeError('unexpected model/tool gate after restart')
            skill = result['skills']
            if skill.get('runtime_enabled') is not True or skill.get('backend') != 'colima':
                raise RuntimeError('unexpected external Skill deployment after restart')
            if skill.get('blockers') != []:
                raise OSError('external Skill is not ready yet')
            if skill.get('image_id') != expected_image:
                raise RuntimeError('unexpected external Skill deployment after restart')
            return result
        except (OSError, ValueError):
            time.sleep(min(1, max(0, deadline - time.monotonic())))
    raise RuntimeError('deployment health deadline exhausted')


def main():
    previous = sys.argv[1]
    assert re.fullmatch('[a-f0-9]{40}', previous)
    work_item = sys.argv[2] if len(sys.argv) > 2 else 'ha0052'
    assert work_item in {'ha0052', 'ha0054', 'ha0055', 'ha0056'}
    commit = run('git', 'rev-parse', 'HEAD')
    assert not run('git', 'status', '--porcelain')
    config = ROOT / 'deploy/local.macos.plist'
    desired = plistlib.loads(config.read_bytes())
    assert desired['EnvironmentVariables'] == {
        'HARNESS_SANDBOX_BACKEND': 'colima', 'HARNESS_EXTERNAL_SKILLS': 'enabled'}
    run('plutil', '-lint', str(config))
    image = run('/opt/homebrew/bin/docker', '--context', 'colima', 'image', 'inspect',
                'harnessagent-external-skill:0.1', '--format', '{{.Id}}')
    assert image.startswith('sha256:')
    backup = ROOT / '.local/backups' / (work_item + '-' + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ'))
    backup.mkdir(parents=True, mode=0o700)
    old = run('git', 'show', previous + ':deploy/local.macos.plist')
    (backup / 'previous.plist').write_text(old)
    db = ROOT / '.local/harness.db'
    with sqlite3.connect('file:' + str(db) + '?mode=ro', uri=True) as source:
        with sqlite3.connect(backup / 'harness.db') as target:
            source.backup(target)
            assert target.execute('PRAGMA integrity_check').fetchone()[0] == 'ok'
    (backup / 'harness.db').chmod(0o600)
    phase = 'bootout'
    try:
        run('launchctl', 'bootout', LABEL)
        phase = 'bootstrap'
        attempts = bootstrap(config)
        phase = 'health'
        status = healthy(image)
    except Exception as activation_error:
        recovery = {'scope': 'previous_plist_only', 'healthy': False, 'phase': 'bootout'}
        try:
            subprocess.run(['launchctl', 'bootout', LABEL], capture_output=True, timeout=10)
            recovery['phase'] = 'bootstrap'
            recovery['bootstrap_attempts'] = bootstrap(backup / 'previous.plist')
            recovery['phase'] = 'health'
            recovery['health'] = healthy(image)
            recovery['healthy'] = True
            recovery['phase'] = 'verified'
        except Exception as recovery_error:
            recovery['error_type'] = type(recovery_error).__name__
            if isinstance(recovery_error, subprocess.CalledProcessError):
                recovery['exit_code'] = recovery_error.returncode
        failure = {'commit': commit, 'backup': str(backup), 'activation_succeeded': False,
                   'phase': phase, 'error_type': type(activation_error).__name__, 'recovery': recovery}
        if isinstance(activation_error, subprocess.CalledProcessError):
            failure['exit_code'] = activation_error.returncode
        (backup / 'activation-failure.json').write_text(json.dumps(failure, indent=2) + '\n')
        raise RuntimeError('Activation failed; previous plist recovery healthy=' +
                           str(recovery['healthy']) + '; see activation-failure.json') from activation_error
    result = dict(commit=commit, backup=str(backup), database=str(db), runtime=status['skills'],
                  health=status['health'], agent_runtime=status['agent_runtime'], bootstrap_attempts=attempts)
    (backup / 'deployment.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
