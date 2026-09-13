"""Build HA-0017 Evidence for offline Replan adapter admission."""
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from xml.etree import ElementTree


ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / 'harness/evidence/HA-0017'
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
    summary = junit_summary(tests_path)
    if summary['tests'] < 142 or summary['failures'] or summary['errors']:
        raise SystemExit('replan adapter admission evidence does not satisfy test acceptance checks')
    from adapters.local import LocalAnalyticsAdapter
    from backend.execution_control import assess_replan_adapter
    current_local = assess_replan_adapter(LocalAnalyticsAdapter().describe())
    if current_local != {
        'adapter_id': 'local_analytics', 'adapter_version': '1.1.0', 'engine': 'engine_mock_analytics',
        'status': 'eligible_for_runtime_probe', 'missing_capabilities': [],
        'runtime_enabled': False,
    }:
        raise SystemExit('current local adapter admission result changed')
    artifacts = ('all-tests.xml', 'acceptance.md')
    manifest = {
        'task': 'HA-0017',
        'checked_at': datetime.now(timezone.utc).isoformat(),
        'status': 'passed',
        'scope': 'historical HA-0017 offline descriptor admission; current descriptor recorded after ADR-0018',
        'model_calls_by_harness': 0,
        'adapter_probe_executed': False,
        'product_run_created_or_restored': False,
        'runtime_replan_api_exposed': False,
        'test_summary': summary,
        'historical_local_adapter_admission': {
            'adapter_id': 'local_analytics', 'adapter_version': '1.0.0', 'engine': 'engine_mock_analytics',
            'status': 'ineligible', 'missing_capabilities': ['state.checkpoint', 'state.restore'],
            'runtime_enabled': False,
        },
        'current_local_adapter_admission': current_local,
        'artifacts': {name: {'sha256': sha256(EVIDENCE / name)} for name in artifacts},
    }
    (EVIDENCE / 'manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps({'task': manifest['task'], 'status': manifest['status'], 'local_status': current_local['status']}, ensure_ascii=False))


if __name__ == '__main__':
    main()
