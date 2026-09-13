"""Build HA-0021 Evidence for the ADR-0020 local Replan Gap State slice."""
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from xml.etree import ElementTree


ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / 'harness/evidence/HA-0021'
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def junit_summary(path):
    root = ElementTree.parse(path).getroot()
    suites = [root] if root.tag == 'testsuite' else list(root.findall('testsuite'))
    return {name: sum(int(suite.attrib.get(name, '0')) for suite in suites)
            for name in ('tests', 'failures', 'errors', 'skipped')}


def main():
    tests_path = EVIDENCE / 'all-tests.xml'
    browser_path = EVIDENCE / 'browser-replan-gap.json'
    summary = junit_summary(tests_path)
    browser = json.loads(browser_path.read_text())
    required_browser_checks = {
        'temporary_deployment', 'artifact_failure_event_fixture', 'replan_proposed', 'try_no_run',
        'confirm_creates_bound_run', 'source_terminal_unchanged', 'artifacts_published',
        'checkpoint_verified', 'gap_created_and_resolved', 'no_reinspect',
    }
    if summary['tests'] < 163 or summary['failures'] or summary['errors']:
        raise SystemExit('replan gap evidence does not satisfy full regression acceptance')
    if (not required_browser_checks.issubset(browser.get('checks', [])) or browser.get('errors')
            or browser.get('model_calls') != 0 or browser.get('network_calls_by_adapter') != 0
            or browser.get('arbitrary_code_calls') != 0):
        raise SystemExit('replan gap browser acceptance changed')

    artifacts = (
        'all-tests.xml', 'browser-replan-gap.json', 'replan-gap-try-ready.png',
        'replan-gap-confirm-ready.png', 'replan-gap-restored-workbench.png', 'acceptance.md',
    )
    manifest = {
        'task': 'HA-0021', 'checked_at': datetime.now(timezone.utc).isoformat(), 'status': 'passed',
        'scope': 'ADR-0020 Gap State for the ADR-0019 deterministic local Replan only',
        'gap_state': {
            'source_failure_code': 'ARTIFACT_PUBLICATION_FAILED', 'required_by': 'node_publish',
            'type': 'evidence', 'severity': 'core', 'resolvable_action_ids': ['artifact.publish'],
            'created_atomically_with_failure_event': True, 'proposal_requires_open_gap': True,
            'resolved_only_after_bound_recovery_success': True,
            'try_cancel_and_failed_recovery_leave_open': True,
        },
        'runtime_capabilities': {
            'model_calls': 0, 'network_calls_by_adapter': 0, 'arbitrary_code_calls': 0,
            'new_failure_kinds': False, 'caller_editable_gap': False,
        },
        'test_summary': summary, 'browser_report': browser,
        'artifacts': {name: {'sha256': sha256(EVIDENCE / name)} for name in artifacts},
    }
    (EVIDENCE / 'manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps({'task': manifest['task'], 'status': manifest['status'], 'tests': summary['tests'],
                      'browser_checks': len(browser['checks'])}, ensure_ascii=False))


if __name__ == '__main__':
    main()
