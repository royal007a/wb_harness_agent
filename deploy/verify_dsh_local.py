"""Read-only acceptance of the dedicated local job, with an explicit release SHA."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import urllib.request

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--release', required=True)
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    base = 'http://127.0.0.1:8876'
    def get(path):
        with urllib.request.urlopen(base + path, timeout=10) as response:
            return response.read()
    runtime = json.loads(get('/api/local/dsh/runtime'))
    assert runtime['release'] == args.release
    job = subprocess.check_output(['launchctl', 'list', 'local.harnessagent.dsh-session'], text=True)
    pid = int(re.search(r'"PID"\s*=\s*(\d+)', job).group(1))
    listeners = subprocess.check_output(['lsof', '-nP', '-iTCP:8876', '-sTCP:LISTEN', '-Fp'], text=True)
    assert {int(line[1:]) for line in listeners.splitlines() if line.startswith('p')} == {pid}
    browser = json.loads((ROOT / 'harness/evidence/HA-0077/browser.json').read_text())
    modes = set()
    for item in browser['runs']:
        detail = json.loads(get('/api/local/dsh/runs/' + item['id']))
        assert detail['run']['status'] == 'succeeded'
        assert detail['budget'] == item['budget']
        assert detail['artifacts'] == item['artifacts']
        for artifact in detail['artifacts']:
            content = get('/api/v1/artifacts/' + artifact['id'] + '/content')
            assert hashlib.sha256(content).hexdigest() == artifact['sha256']
            assert len(content) == artifact['size_bytes']
        modes.add(item['mode'])
    assert modes == {'integration_probe', 'real_provider'}
    root = ROOT / '.local/dsh-runs'
    assert not list(root.glob('run-*'))
    assert not list((root / '.registry').glob('*.json'))
    receipt = {'url': base + '/dsh', 'release': runtime['release'], 'pid': pid,
        'process_started_at': subprocess.check_output(['ps', '-p', str(pid), '-o', 'lstart='], text=True).strip(),
        'listener_matches_job_pid': True, 'browser_execution_release': browser['release'],
        'persisted_run_ids': [r['id'] for r in browser['runs']],
        'artifact_hashes_verified': True, 'owned_workspace_residue': 0,
        'database': '.local/dsh.db', 'scope': 'authorized_login_session_loopback_only',
        'not_evidence': ['reboot_autostart', '132_deployment', 'OS_sandbox', 'analysis_semantic_correctness']}
    Path(args.output).write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps(receipt, ensure_ascii=False))


if __name__ == '__main__':
    main()
