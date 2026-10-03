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


def run(*args):
    return subprocess.check_output(args, cwd=ROOT, text=True).strip()


def main():
    previous = sys.argv[1]
    assert re.fullmatch('[a-f0-9]{40}', previous)
    work_item = sys.argv[2] if len(sys.argv) > 2 else 'ha0052'
    assert work_item in {'ha0052', 'ha0054', 'ha0055'}
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
    run('launchctl', 'bootout', LABEL)
    try:
        # launchd may still be delivering termination. Wait for the old listener.
        time.sleep(1)
        run('launchctl', 'bootstrap', f'gui/{os.getuid()}', str(config))
        for attempt in range(40):
            try:
                with urllib.request.urlopen('http://127.0.0.1:8765/api/local/external-skills/runtime', timeout=3) as response:
                    status = json.load(response)
                assert status['runtime_enabled'] and not status['blockers'] and status['backend'] == 'colima'
                break
            except (OSError, AssertionError):
                if attempt == 39:
                    raise
                time.sleep(.5)
    except Exception:
        subprocess.run(['launchctl', 'bootout', LABEL], capture_output=True)
        time.sleep(1)
        run('launchctl', 'bootstrap', f'gui/{os.getuid()}', str(backup / 'previous.plist'))
        raise
    result = dict(commit=commit, backup=str(backup), database=str(db), runtime=status)
    (backup / 'deployment.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
