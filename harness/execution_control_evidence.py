"""Build HA-0015 Evidence for the no-model, no-runtime execution-control contract."""
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from xml.etree import ElementTree


ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / 'harness/evidence/HA-0015'
SCHEMA = ROOT / 'specs/v1/execution-control.schema.json'
FIXTURE = ROOT / 'fixtures/execution-control-evaluation-v1.json'
REDUCER = ROOT / 'backend/execution_control.py'


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def junit_summary(path):
    root = ElementTree.parse(path).getroot()
    suites = [root] if root.tag == 'testsuite' else list(root.findall('testsuite'))
    return {name: sum(int(suite.attrib.get(name, '0')) for suite in suites)
            for name in ('tests', 'failures', 'errors', 'skipped')}


def main():
    tests_path = EVIDENCE / 'all-tests.xml'
    evaluation_path = EVIDENCE / 'evaluation-results.json'
    summary = junit_summary(tests_path)
    evaluation = json.loads(evaluation_path.read_text())
    reducer_text = REDUCER.read_text()
    if (summary['tests'] < 140 or summary['failures'] or summary['errors']
            or set(evaluation) != {'evaluation_version', 'classification', 'case_count', 'passed_case_ids', 'failed_case_ids'}
            or evaluation.get('evaluation_version') != 'execution-control-evaluation@1'
            or evaluation.get('classification') != 'synthetic_deidentified'
            or evaluation.get('case_count') != 13
            or evaluation.get('failed_case_ids') != []
            or len(evaluation.get('passed_case_ids', [])) != 13
            or 'backend.service' in reducer_text or 'requests.' in reducer_text):
        raise SystemExit('execution-control evidence does not satisfy acceptance checks')
    artifacts = ('all-tests.xml', 'evaluation-results.json', 'acceptance.md')
    manifest = {
        'task': 'HA-0015',
        'checked_at': datetime.now(timezone.utc).isoformat(),
        'status': 'passed',
        'scope': 'offline execution-control contract and synthetic evaluation only',
        'model_calls_by_harness': 0,
        'product_run_created_or_restored': False,
        'runtime_replan_api_exposed': False,
        'test_summary': summary,
        'fixture': {
            'version': evaluation['evaluation_version'],
            'classification': evaluation['classification'],
            'case_count': evaluation['case_count'],
            'sha256': sha256(FIXTURE),
        },
        'contract': {'sha256': sha256(SCHEMA)},
        'reducer': {'sha256': sha256(REDUCER), 'runtime_imports': False},
        'artifacts': {name: {'sha256': sha256(EVIDENCE / name)} for name in artifacts},
    }
    (EVIDENCE / 'manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps({'task': manifest['task'], 'status': manifest['status'], 'test_summary': summary}, ensure_ascii=False))


if __name__ == '__main__':
    main()
