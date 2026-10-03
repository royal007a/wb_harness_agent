"""Promote a committed staging checkout on the approved 132 host.

Run as root over SSH after local acceptance. Preserves credentials, runtime
environment and service-owned data. Does not install dependencies or enable AI.
"""
import json
import os
import re
import shutil
import sqlite3
import subprocess
import sys
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path


LIVE = Path('/opt/harnessagent')
PYTHON = LIVE / '.venv/bin/python'
TEST_PYTHON = Path('/opt/harnessagent-test-env/bin/python')
SNIPPET = Path('/etc/nginx/snippets/harnessagent.conf')
SITE = Path('/etc/nginx/sites-available/workbench')
PRESERVE = ['.venv/', '.local/', 'data/', 'node_modules/', '__pycache__/', 'evidence/']


def run(*args, cwd=None):
    return subprocess.check_output(args, cwd=cwd, text=True).rstrip('\n')


def sync(source):
    subprocess.run(['rsync', '-a', '--delete', *['--exclude=' + p for p in PRESERVE],
                    str(source) + '/', str(LIVE) + '/'], check=True)


def healthy():
    for _ in range(30):
        try:
            with urllib.request.urlopen('http://127.0.0.1:8765/api/v1/health', timeout=2) as response:
                health = json.load(response)
                assert health['status'] == 'ok' and health['model_calls_enabled'] is False
                return health
        except (OSError, AssertionError):
            time.sleep(0.3)
    raise RuntimeError('Service health check failed')


def main():
    assert os.geteuid() == 0, 'Run over the approved root SSH session'
    stage = Path(sys.argv[1]).resolve()
    commit = sys.argv[2]
    assert re.fullmatch('[a-f0-9]{40}', commit)
    work_item = sys.argv[3] if len(sys.argv) > 3 else 'ha0051'
    assert work_item in {'ha0051', 'ha0052', 'ha0054', 'ha0055'}
    activate_skills = work_item == 'ha0052'
    override = Path('/etc/systemd/system/harnessagent.service.d/external-skills.conf')
    assert stage.parent == Path('/opt/harnessagent-releases') and stage.name == work_item + '-' + commit[:12]
    assert run('git', '-C', str(stage), 'rev-parse', 'HEAD') == commit
    assert not run('git', '-C', str(stage), 'status', '--porcelain')
    pid = int(run('systemctl', 'show', 'harnessagent', '--property=MainPID', '--value'))
    assert pid > 1
    # Read only the necessary service setting; never dump the environment.
    environment = dict(entry.split(b'=', 1) for entry in Path(f'/proc/{pid}/environ').read_bytes().split(b'\0') if b'=' in entry)
    db_path = Path(environment[b'HARNESS_DB'].decode()).resolve()
    assert db_path.is_relative_to('/var/lib/harnessagent') and db_path.is_file()
    assert environment.get(b'HARNESS_AGENT_RUNTIME', b'disabled') != b'enabled'
    previous = run('git', '-c', 'safe.directory=' + str(LIVE), '-C', str(LIVE), 'rev-parse', 'HEAD')
    # Only known deployment omissions in evidence may be dirty, not app code.
    changes = run('git', '-c', 'safe.directory=' + str(LIVE), '-C', str(LIVE), 'status', '--porcelain')
    assert all(line.startswith(' D harness/evidence/') for line in changes.splitlines()), 'Unexpected live edits'
    assert (stage / 'requirements.txt').read_bytes() == (LIVE / 'requirements.txt').read_bytes(), 'Dependency changes need separate provisioning'
    run(str(PYTHON), '-m', 'pip', 'check')
    # Optional SDK test dependencies stay outside the live runtime. Provision
    # this separate environment from requirements-claude.txt before release.
    preflight = TEST_PYTHON if TEST_PYTHON.is_file() else PYTHON
    subprocess.run([str(preflight), '-m', 'pytest', '-q'], cwd=stage, check=True)
    subprocess.run([str(PYTHON), '-m', 'pytest', '-q', 'tests/test_frontend_paths.py',
                    'tests/test_workbench.py'], cwd=stage, check=True)
    if activate_skills:
        prebuilt = os.environ.get('HARNESS_PREBUILT_EXTERNAL_IMAGE')
        if prebuilt:
            # Explicit operator handoff for hosts unable to reach the registry.
            # Transfer a locally built linux/amd64 image via SSH, verify its
            # immutable ID, and still run the real isolation probes on this host.
            assert re.fullmatch('sha256:[a-f0-9]{64}', prebuilt)
            image = json.loads(run('docker', '--host', 'unix:///var/run/docker.sock',
                                  'image', 'inspect', 'harnessagent-external-skill:0.1'))[0]
            assert image['Id'] == prebuilt and image['Architecture'] == 'amd64' and image['Os'] == 'linux'
        else:
            subprocess.run(['docker', '--host', 'unix:///var/run/docker.sock', 'build',
                            '-f', 'sandbox/external-skill.Dockerfile', '-t', 'harnessagent-external-skill:0.1',
                            'sandbox'], cwd=stage, check=True, timeout=240)
        subprocess.run([str(PYTHON), '-m', 'pytest', '-q', 'tests/test_external_skills.py'], cwd=stage,
                       env={**os.environ, 'HARNESS_SANDBOX_BACKEND': 'linux-docker',
                            'HARNESS_EXTERNAL_SKILLS': 'disabled', 'HARNESS_DOCKER_TESTS': '1'},
                       check=True, timeout=180)
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    backup = Path('/var/backups/harnessagent') / (work_item + '-' + stamp)
    backup.mkdir(parents=True, mode=0o700)
    shutil.copy2(SNIPPET, backup / 'nginx-snippet.conf')
    shutil.copy2(SITE, backup / 'nginx-site.conf')
    had_override = override.exists()
    if had_override:
        shutil.copy2(override, backup / 'external-skills.conf')
    subprocess.run(['tar', *['--exclude=./' + p.rstrip('/') for p in PRESERVE],
                    '-czf', str(backup / 'application.tar.gz'), '-C', str(LIVE), '.'], check=True)
    stopped = False
    promoted = False
    try:
        run('systemctl', 'stop', 'harnessagent')
        stopped = True
        with sqlite3.connect('file:' + str(db_path) + '?mode=ro', uri=True) as source:
            with sqlite3.connect(backup / 'harness.db') as dest:
                source.backup(dest)
                assert dest.execute('PRAGMA integrity_check').fetchone()[0] == 'ok'
        (backup / 'harness.db').chmod(0o600)
        promoted = True  # also recover if rsync fails partway through
        sync(stage)
        if activate_skills:
            override.parent.mkdir(exist_ok=True)
            shutil.copyfile(LIVE / 'deploy/external-skills.service.conf', override)
            run('systemctl', 'daemon-reload')
        shutil.copyfile(LIVE / 'deploy/nginx-harnessagent.conf', SNIPPET)
        site = SITE.read_text()
        http_block, remainder = site.split('\nserver {', 1)
        include = '    include /etc/nginx/snippets/harnessagent.conf;'
        if include not in http_block:
            anchor = '    location / {\n        return 301 https://$host$request_uri;'
            assert http_block.count(anchor) == 1, 'Unexpected HTTP server layout'
            http_block = http_block.replace(anchor, include + '\n' + anchor)
            SITE.write_text(http_block + '\nserver {' + remainder)
        run('nginx', '-t')
        run('systemctl', 'start', 'harnessagent')
        health = healthy()
        run('systemctl', 'reload', 'nginx')
        if activate_skills:
            with urllib.request.urlopen('http://127.0.0.1:8765/api/local/external-skills/runtime', timeout=10) as response:
                skill_status = json.load(response)
            assert skill_status['runtime_enabled'] is True and not skill_status['blockers']
            assert skill_status['backend'] == 'linux-docker'
    except Exception:
        if promoted:
            rollback = backup / 'rollback'
            rollback.mkdir()
            run('tar', '-xzf', str(backup / 'application.tar.gz'), '-C', str(rollback))
            sync(rollback)
            shutil.copy2(backup / 'nginx-snippet.conf', SNIPPET)
            shutil.copy2(backup / 'nginx-site.conf', SITE)
            if activate_skills:
                if had_override:
                    shutil.copy2(backup / 'external-skills.conf', override)
                elif override.exists():
                    override.unlink()
                run('systemctl', 'daemon-reload')
            run('nginx', '-t')
            run('systemctl', 'reload', 'nginx')
        if stopped:
            run('systemctl', 'restart', 'harnessagent')
            healthy()
        raise
    result = dict(commit=commit, previous_commit=previous, deployed_at=stamp, database=str(db_path),
                  backup=str(backup), health=health, runtime_environment_preserved=True,
                  credentials_unchanged=True, public_url='http://118.196.123.132/harness/')
    if activate_skills:
        result['external_skills'] = skill_status
    (backup / 'deployment.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
