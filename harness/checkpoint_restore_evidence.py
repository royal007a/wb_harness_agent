"""Build HA-0019 evidence for the constrained local Product restore slice."""
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from xml.etree import ElementTree


ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / 'harness/evidence/HA-0019'
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
    browser_path = EVIDENCE / 'browser-checkpoint-restore.json'
    summary = junit_summary(tests_path)
    browser = json.loads(browser_path.read_text())
    required_browser_checks = {
        'temporary_deployment', 'checkpoint_visible_after_fixture_failure', 'restore_button',
        'new_run_created', 'source_terminal_unchanged', 'artifacts_published', 'no_reinspect',
    }
    if summary['tests'] < 141 or summary['failures'] or summary['errors']:
        raise SystemExit('checkpoint restore evidence does not satisfy full regression acceptance')
    if (not required_browser_checks.issubset(browser.get('checks', [])) or browser.get('errors')
            or browser.get('model_calls') != 0 or browser.get('network_calls_by_adapter') != 0):
        raise SystemExit('checkpoint restore browser acceptance changed')

    from adapters.local import LocalAnalyticsAdapter
    from backend.execution_control import assess_replan_adapter
    descriptor = LocalAnalyticsAdapter().describe()
    admission = assess_replan_adapter(descriptor)
    if admission != {
        'adapter_id': 'local_analytics', 'adapter_version': '1.1.0', 'engine': 'engine_mock_analytics',
        'status': 'eligible_for_runtime_probe', 'missing_capabilities': [], 'runtime_enabled': False,
    }:
        raise SystemExit('local adapter descriptor admission changed')

    artifacts = (
        'all-tests.xml', 'browser-checkpoint-restore.json', 'checkpoint-restore-eligible.png',
        'checkpoint-restore-workbench.png', 'acceptance.md',
    )
    manifest = {
        'task': 'HA-0019',
        'checked_at': datetime.now(timezone.utc).isoformat(),
        'status': 'passed',
        'scope': 'ADR-0018 constrained fixed analytics Product checkpoint/restore only',
        'source_run_statuses': ['failed', 'expired'],
        'forbidden_source_run_statuses': ['queued', 'running', 'cancelled', 'succeeded'],
        'runtime_capabilities': {
            'checkpoint_boundary': 'after_resource_inspect',
            'same_task_only': True,
            'dynamic_replan_enabled': False,
            'model_calls': 0,
            'network_calls_by_adapter': 0,
            'arbitrary_code_enabled': False,
        },
        'binding_checks': ['checkpoint', 'state', 'source_run', 'Task', 'resource', 'adapter', 'effective_permissions', 'source_effective_limits', 'remaining_limits'],
        'test_summary': summary,
        'browser_report': browser,
        'adapter_descriptor': descriptor,
        'offline_dynamic_replan_admission': admission,
        'artifacts': {name: {'sha256': sha256(EVIDENCE / name)} for name in artifacts},
    }
    (EVIDENCE / 'manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps({'task': manifest['task'], 'status': manifest['status'], 'tests': summary['tests'],
                      'browser_checks': len(browser['checks'])}, ensure_ascii=False))


if __name__ == '__main__':
    main()
