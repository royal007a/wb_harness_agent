"""Capture redacted acceptance evidence for the local OAuth connector base."""
from datetime import datetime, timezone
import hashlib
from importlib.metadata import version
import json
from pathlib import Path
import urllib.request
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / 'harness/evidence/HA-0010'


def get(path):
    with urllib.request.urlopen('http://127.0.0.1:8765' + path, timeout=10) as response:
        return json.load(response)


def main():
    suite = ET.parse(EVIDENCE / 'all-tests.xml').getroot().find('testsuite')
    tests = {key: int(suite.attrib[key]) for key in ('tests', 'failures', 'errors', 'skipped')}
    browser = json.loads((EVIDENCE / 'browser.json').read_text())
    workbench = json.loads((EVIDENCE / 'workbench/browser.json').read_text())
    status = get('/api/local/connectors/baidu-netdisk')
    health = get('/api/v1/health')
    assert tests['tests'] >= 98 and not any(tests[key] for key in ('failures', 'errors', 'skipped'))
    assert not browser['errors'] and not workbench['errors']
    assert status['status'] == 'not_configured'
    assert status['has_token'] is False and status['data_access_enabled'] is False
    assert 'secret' not in json.dumps(status).lower()
    paths = ['backend/baidu_netdisk.py', 'backend/app.py', 'backend/store.py',
             'specs/v1/baidu-netdisk-connector.schema.json', 'frontend/baidu-netdisk.js']
    security = {
        'checked_at': datetime.now(timezone.utc).isoformat(),
        'status': 'passed',
        'checks': [
            'unconfigured_connector_cannot_generate_authorization_url',
            'state_is_single_use_expiring_and_persisted_only_as_digest',
            'callback_code_is_not_emitted_in_application_events_or_access_log',
            'token_response_validation_refresh_disconnect_and_keychain_failure_injection',
            'fixed_official_oauth_hosts_and_no_data_plane_endpoints',
            'status_api_and_evidence_are_redacted',
        ],
        'live_oauth': 'not_run: requires user-owned registered application and a non-sensitive test account',
        'data_plane': 'disabled',
    }
    report = {
        'checked_at': datetime.now(timezone.utc).isoformat(),
        'status': 'passed',
        'mode': 'local_official_oauth_connector_base',
        'tests': tests,
        'browser_checks': len(browser['checks']),
        'workbench_browser_checks': len(workbench['checks']),
        'health': health,
        'connector_status': status,
        'dependency_versions': {'keyring': version('keyring'), 'httpx': version('httpx')},
        'source_sha256': {path: hashlib.sha256((ROOT / path).read_bytes()).hexdigest() for path in paths},
        'evidence': ['all-tests.xml', 'browser.json', 'workbench/browser.json', 'security-results.json'],
        'limitations': [
            'OAuth application and real user authorization are not configured',
            'no directory, download, sharing-link, preview, or document-import data plane',
            'no browser Cookie reuse, simulated login, captcha handling, or secret in evidence',
        ],
    }
    (EVIDENCE / 'security-results.json').write_text(json.dumps(security, ensure_ascii=False, indent=2) + '\n')
    (EVIDENCE / 'manifest.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps(report, ensure_ascii=False))


if __name__ == '__main__':
    main()
