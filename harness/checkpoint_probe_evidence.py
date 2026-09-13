"""Build HA-0018 Evidence for the isolated checkpoint/restore probe."""
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from xml.etree import ElementTree


ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / 'harness/evidence/HA-0018'
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
    if summary['tests'] < 143 or summary['failures'] or summary['errors']:
        raise SystemExit('checkpoint probe evidence does not satisfy test acceptance checks')
    from harness.checkpoint_restore_probe import DeterministicCheckpointProbeAdapter, run_probe
    report = run_probe()
    expected = {
        'mode': 'isolated_deterministic_checkpoint_restore_probe',
        'replan_statuses': ['proposed', 'trying', 'awaiting_confirmation', 'confirmed'],
        'restored_next_node_id': 'node_publish', 'restored_completed_node_ids': ['node_inspect'],
        'model_calls': 0, 'tool_calls': 0, 'network_calls': 0,
        'product_run_created_or_restored': False, 'runtime_route_registered': False,
    }
    if any(report.get(key) != value for key, value in expected.items()):
        raise SystemExit('checkpoint probe report changed')
    adapter = DeterministicCheckpointProbeAdapter()
    checkpoint, payload = adapter.checkpoint({'next_node_id': 'node_publish', 'completed_node_ids': ['node_inspect']})
    rejected = []
    for field in ('checkpoint_digest', 'state_digest', 'adapter_digest', 'resource_digest',
                  'effective_permissions_digest', 'remaining_limits_digest'):
        try:
            adapter.restore({**checkpoint, field: 'b' * 64}, payload)
        except ValueError:
            rejected.append(field)
    if len(rejected) != 6:
        raise SystemExit('checkpoint binding tamper was not rejected')
    artifacts = ('all-tests.xml', 'acceptance.md')
    manifest = {
        'task': 'HA-0018', 'checked_at': datetime.now(timezone.utc).isoformat(), 'status': 'passed',
        'scope': 'isolated deterministic checkpoint/restore probe only',
        'model_calls_by_harness': 0, 'tool_calls_by_harness': 0, 'network_calls_by_harness': 0,
        'product_run_created_or_restored': False, 'runtime_route_registered': False,
        'test_summary': summary, 'probe_report': report,
        'rejected_tampered_binding_fields': rejected,
        'artifacts': {name: {'sha256': sha256(EVIDENCE / name)} for name in artifacts},
    }
    (EVIDENCE / 'manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps({'task': manifest['task'], 'status': manifest['status'], 'rejected': rejected}, ensure_ascii=False))


if __name__ == '__main__':
    main()
