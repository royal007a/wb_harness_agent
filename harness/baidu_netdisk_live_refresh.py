"""Run one user-approved, redacted OAuth refresh probe; never access file APIs."""
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.analysis import Problem
from backend.baidu_netdisk import BaiduNetdiskConnector

APP_KEY_ENV = 'HARNESS_BAIDUPAN_CLIENT_ID'
LAUNCHD_LABEL = 'local.harnessagent.workbench'


def valid_app_key(value):
    return isinstance(value, str) and 8 <= len(value) <= 128 and not any(char.isspace() for char in value)


def load_launchd_app_key(*, environ=os.environ, run=subprocess.run, uid=os.getuid()):
    if valid_app_key(environ.get(APP_KEY_ENV)):
        return
    result = run(['launchctl', 'getenv', APP_KEY_ENV], check=False, text=True,
                 stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    candidate = result.stdout.strip() if result.returncode == 0 else ''
    if not valid_app_key(candidate):
        detail = run(['launchctl', 'print', f'gui/{uid}/{LAUNCHD_LABEL}'], check=False, text=True,
                     stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
        match = re.search(r'^\s*HARNESS_BAIDUPAN_CLIENT_ID => ([^\r\n]+)$', detail.stdout, re.MULTILINE)
        candidate = match.group(1).strip() if detail.returncode == 0 and match else ''
    if not valid_app_key(candidate):
        raise RuntimeError('公开 App Key 未配置在当前 login session。')
    environ[APP_KEY_ENV] = candidate


def main():
    try:
        load_launchd_app_key()
    except RuntimeError as exc:
        raise SystemExit('拒绝：' + str(exc)) from exc
    connector = BaiduNetdiskConnector(store=None)
    before = connector.status()
    if before['status'] != 'connected' or not before['has_token']:
        raise SystemExit('拒绝：仅能对已连接的本机授权执行刷新验证。')
    try:
        result = connector.refresh_for_verification()
    except Problem as exc:
        raise SystemExit('刷新验证失败：' + exc.code) from exc
    if result != {'provider': 'baidu_netdisk', 'refreshed': True, 'status': 'connected',
                  'has_token': True, 'data_access_enabled': False}:
        raise SystemExit('刷新验证未满足连接器安全契约。')
    report = {'checked_at': datetime.now(timezone.utc).isoformat(), 'status': 'passed',
              'operation': 'official_oauth_refresh_only', 'result': result,
              'file_api_calls': 0, 'token_material_emitted': False}
    directory = ROOT / 'harness/evidence/HA-0011'
    directory.mkdir(parents=True, exist_ok=True)
    (directory / 'live-refresh.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps(report, ensure_ascii=False))


if __name__ == '__main__':
    main()
