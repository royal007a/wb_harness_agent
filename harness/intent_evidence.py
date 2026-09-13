"""Build a redacted HA-0013 evidence manifest from deterministic artifacts."""
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from xml.etree import ElementTree


ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / 'harness/evidence/HA-0013'


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
    browser_path = EVIDENCE / 'browser.json'
    summary = junit_summary(tests_path)
    evaluation = json.loads(evaluation_path.read_text())
    browser = json.loads(browser_path.read_text())
    expected_metrics = {'decision_accuracy', 'intent_accuracy', 'missing_slots_exact_accuracy',
                        'route_accuracy', 'rejection_precision', 'rejection_recall'}
    if (summary['tests'] < 130 or summary['failures'] or summary['errors']
            or evaluation.get('failures')
            or set(evaluation.get('metrics', {})) != expected_metrics
            or any(value != 1.0 for value in evaluation['metrics'].values())
            or browser.get('errors')
            or 'intent_preflight' not in browser.get('checks', [])):
        raise SystemExit('intent evidence does not satisfy acceptance checks')
    artifacts = ('all-tests.xml', 'evaluation-results.json', 'browser.json', 'intent-preflight.png')
    manifest = {
        'task': 'HA-0013',
        'checked_at': datetime.now(timezone.utc).isoformat(),
        'status': 'passed',
        'scope': 'deterministic local intent preflight only',
        'model_calls': 0,
        'persistent_preflight_input': False,
        'test_summary': summary,
        'evaluation_metrics': evaluation['metrics'],
        'artifacts': {name: {'sha256': sha256(EVIDENCE / name)} for name in artifacts},
    }
    (EVIDENCE / 'manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps({'task': manifest['task'], 'status': manifest['status'],
                      'test_summary': summary, 'model_calls': 0}, ensure_ascii=False))


if __name__ == '__main__':
    main()
