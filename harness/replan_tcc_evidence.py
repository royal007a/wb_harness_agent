"""Build HA-0020 Evidence for the ADR-0019 deterministic local TCC slice."""
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from xml.etree import ElementTree


ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / 'harness/evidence/HA-0020'
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
    browser_path = EVIDENCE / 'browser-replan-tcc.json'
    summary = junit_summary(tests_path)
    browser = json.loads(browser_path.read_text())
    required_browser_checks = {
        'temporary_deployment', 'artifact_failure_event_fixture', 'replan_proposed', 'try_no_run',
        'confirm_creates_bound_run', 'source_terminal_unchanged', 'artifacts_published',
        'checkpoint_verified', 'no_reinspect',
    }
    if summary['tests'] < 162 or summary['failures'] or summary['errors']:
        raise SystemExit('replan TCC evidence does not satisfy full regression acceptance')
    if (not required_browser_checks.issubset(browser.get('checks', [])) or browser.get('errors')
            or browser.get('model_calls') != 0 or browser.get('network_calls_by_adapter') != 0
            or browser.get('arbitrary_code_calls') != 0):
        raise SystemExit('replan TCC browser acceptance changed')

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
        'all-tests.xml', 'browser-replan-tcc.json', 'replan-try-ready.png', 'replan-confirm-ready.png',
        'replan-restored-workbench.png', 'acceptance.md',
    )
    manifest = {
        'task': 'HA-0020', 'checked_at': datetime.now(timezone.utc).isoformat(), 'status': 'passed',
        'scope': 'ADR-0019 deterministic local analytics Replan TCC only',
        'admission': {
            'source_failure_code': 'ARTIFACT_PUBLICATION_FAILED',
            'source_statuses': ['failed'],
            'candidate_plan_nodes': ['checkpoint.verify', 'artifact.publish', 'run.final_answer'],
            'caller_plan_or_goal_input': False,
        },
        'tcc': {
            'try_creates_product_run': False,
            'confirm_creates_one_bound_product_run': True,
            'cancel_creates_product_run': False,
            'confirm_compare_and_swap': ['candidate_plan', 'checkpoint', 'Task', 'resource', 'adapter',
                                          'effective_permissions', 'remaining_limits'],
            'post_try_drift_expires_confirmation': True,
        },
        'runtime_capabilities': {
            'model_calls': 0, 'network_calls_by_adapter': 0, 'arbitrary_code_calls': 0,
            'cross_task_or_engine_restore': False, 'resource_reinspect': False,
        },
        'test_summary': summary, 'browser_report': browser, 'adapter_descriptor': descriptor,
        'offline_dynamic_replan_admission': admission,
        'artifacts': {name: {'sha256': sha256(EVIDENCE / name)} for name in artifacts},
    }
    (EVIDENCE / 'manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps({'task': manifest['task'], 'status': manifest['status'], 'tests': summary['tests'],
                      'browser_checks': len(browser['checks'])}, ensure_ascii=False))


if __name__ == '__main__':
    main()
