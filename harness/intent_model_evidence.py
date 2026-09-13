"""Build HA-0014 evidence without copying evaluation objectives into Evidence."""
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from xml.etree import ElementTree


ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / 'harness/evidence/HA-0014'
FIXTURE = ROOT / 'fixtures/intent-evaluation-v2.json'
POLICY = ROOT / 'fixtures/intent-evaluation-policy-v1.json'
EXPECTED_BASELINE_GAPS = {
    'ready_column_distribution', 'clarify_view_table', 'reject_external_upload',
    'reject_public_url_export', 'reject_prompt_injection', 'reject_local_secret',
    'reject_host_path', 'reject_email_export',
}


def _sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _junit_summary(path):
    root = ElementTree.parse(path).getroot()
    suites = [root] if root.tag == 'testsuite' else list(root.findall('testsuite'))
    return {name: sum(int(suite.attrib.get(name, '0')) for suite in suites)
            for name in ('tests', 'failures', 'errors', 'skipped')}


def main():
    tests_path = EVIDENCE / 'all-tests.xml'
    baseline_path = EVIDENCE / 'rules-baseline.json'
    fixture = json.loads(FIXTURE.read_text())
    policy = json.loads(POLICY.read_text())
    baseline_text = baseline_path.read_text()
    baseline = json.loads(baseline_text)
    summary = _junit_summary(tests_path)
    objectives = [case['request']['objective'] for case in fixture['cases'] if case['request']['objective'].strip()]
    if (summary['tests'] < 130 or summary['failures'] or summary['errors']
            or baseline.get('evaluation_version') != 'intent-evaluation@2'
            or baseline.get('case_count') != policy['minimum_case_count']
            or baseline.get('candidate') != {'kind': 'rules_baseline', 'version': 'rules@1', 'execution_mode': 'local'}
            or set(baseline.get('failures', [])) != EXPECTED_BASELINE_GAPS
            or any(objective in baseline_text for objective in objectives)):
        raise SystemExit('intent model evaluation evidence does not satisfy acceptance checks')
    artifacts = ('all-tests.xml', 'rules-baseline.json', 'acceptance.md')
    manifest = {
        'task': 'HA-0014',
        'checked_at': datetime.now(timezone.utc).isoformat(),
        'status': 'passed',
        'scope': 'synthetic deidentified offline and shadow evaluation preparation only',
        'model_calls_by_harness': 0,
        'production_data_accessed': False,
        'rules_baseline_is_model_candidate': False,
        'fixture': {
            'version': fixture['fixture_version'],
            'sha256': _sha256(FIXTURE),
            'case_count': len(fixture['cases']),
            'classification': fixture['dataset']['classification'],
        },
        'policy_version': policy['policy_version'],
        'test_summary': summary,
        'baseline_metrics': baseline['metrics'],
        'baseline_gap_case_ids': sorted(EXPECTED_BASELINE_GAPS),
        'artifacts': {name: {'sha256': _sha256(EVIDENCE / name)} for name in artifacts},
    }
    (EVIDENCE / 'manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps({
        'task': manifest['task'], 'status': manifest['status'],
        'test_summary': summary, 'model_calls_by_harness': 0,
    }, ensure_ascii=False))


if __name__ == '__main__':
    main()
