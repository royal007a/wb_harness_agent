"""Start only the separate DSH job in the caller's authorized login session.

No credential is passed through argv/environment/files. This is session-scoped,
not a claim of restart-after-reboot availability. Existing listeners are refused.
"""
import json
from pathlib import Path
import plistlib
import socket
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def main():
    from backend.agent_runtime import KeyringCredentialResolver
    config = plistlib.loads((ROOT / 'deploy/dsh-local.macos.plist').read_bytes())
    env = config['EnvironmentVariables']
    assert config['WorkingDirectory'] == str(ROOT)
    if subprocess.check_output(['git', 'status', '--porcelain'], cwd=ROOT).strip():
        raise RuntimeError('Commit reviewed changes before deployment')
    with socket.socket() as probe:
        if probe.connect_ex(('127.0.0.1', 8876)) == 0:
            raise RuntimeError('Port 8876 is occupied; refuse to replace an unidentified process')
    # Read and discard, never print or transfer the value to launchd/DSH.
    KeyringCredentialResolver().resolve(env['HARNESS_DSH_CREDENTIAL_REF'])
    command = ['launchctl', 'submit', '-l', 'local.harnessagent.dsh-session',
        '-o', config['StandardOutPath'], '-e', config['StandardErrorPath'], '--',
        '/usr/bin/env', '-i', *[f'{key}={value}' for key, value in env.items()],
        config['ProgramArguments'][0], str(ROOT / 'deploy/run_dsh_local.py')]
    subprocess.run(command, cwd=ROOT, check=True)
    print(json.dumps({'submitted': True, 'label': 'local.harnessagent.dsh-session',
                      'url': 'http://127.0.0.1:8876/dsh', 'credential_in_argv_or_env': False}))


if __name__ == '__main__':
    main()
