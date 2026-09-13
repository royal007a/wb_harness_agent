"""Validate redacted HA-0011 OAuth evidence without touching Baidu APIs."""
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from xml.etree import ElementTree


ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / 'harness/evidence/HA-0011'


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    refresh_path = EVIDENCE / 'live-refresh.json'
    tests_path = EVIDENCE / 'all-tests.xml'
    refresh = json.loads(refresh_path.read_text())
    expected = {
        'provider': 'baidu_netdisk',
        'refreshed': True,
        'status': 'connected',
        'has_token': True,
        'data_access_enabled': False,
    }
    if (refresh.get('status') != 'passed'
            or refresh.get('operation') != 'official_oauth_refresh_only'
            or refresh.get('result') != expected
            or refresh.get('file_api_calls') != 0
            or refresh.get('token_material_emitted') is not False):
        raise SystemExit('拒绝：refresh evidence 不满足无数据面、无密契约。')
    report_root = ElementTree.parse(tests_path).getroot()
    suites = [report_root] if report_root.tag == 'testsuite' else list(report_root.findall('testsuite'))
    tests = sum(int(suite.attrib.get('tests', '0')) for suite in suites)
    failures = sum(int(suite.attrib.get('failures', '0')) for suite in suites)
    errors = sum(int(suite.attrib.get('errors', '0')) for suite in suites)
    if tests < 114 or failures or errors:
        raise SystemExit('拒绝：回归测试 evidence 未通过。')
    manifest = {
        'checked_at': datetime.now(timezone.utc).isoformat(),
        'task': 'HA-0011',
        'status': 'passed',
        'scope': 'official OAuth authorization and one refresh verification only',
        'data_plane_calls': 0,
        'token_material_emitted': False,
        'tests': {'passed': tests, 'failures': failures, 'errors': errors},
        'artifacts': {
            name: {'sha256': sha256(EVIDENCE / name)}
            for name in ('configuration-helper-precheck.md', 'configuration-tests.xml',
                         'live-refresh.json', 'all-tests.xml')
        },
    }
    (EVIDENCE / 'manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps({'task': manifest['task'], 'status': manifest['status'],
                      'tests': manifest['tests'], 'data_plane_calls': 0}, ensure_ascii=False))


if __name__ == '__main__':
    main()
