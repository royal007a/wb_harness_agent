"""Evaluate the versioned deterministic intent rules without production data."""
import argparse
import hashlib
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.intent import IntentRouter


def evaluate(cases):
    router = IntentRouter()
    details = []
    expected_rejects = actual_rejects = true_rejects = 0
    counts = {'decision': 0, 'intent': 0, 'missing_slots': 0, 'route': 0}
    for case in cases:
        request = case['request']
        resource = {'id': 'res_fixture'} if request['has_resource'] else None
        result = router.interpret({'objective': request['objective'], **({'resource_id': resource['id']} if resource else {})}, resource)
        expected = case['expected']
        actual_intent = result['intent']['id'] if result['intent'] else None
        matches = {
            'decision': result['decision'] == expected['decision'],
            'intent': actual_intent == expected['intent_id'],
            'missing_slots': result['missing_slots'] == expected['missing_slots'],
            'route': (result['route'] is not None) == expected['has_route'],
        }
        for name, matched in matches.items():
            counts[name] += int(matched)
        expected_rejects += int(expected['decision'] == 'rejected')
        actual_rejects += int(result['decision'] == 'rejected')
        true_rejects += int(expected['decision'] == result['decision'] == 'rejected')
        details.append({'case_id': case['id'], 'actual': {
            'decision': result['decision'], 'intent_id': actual_intent,
            'missing_slots': result['missing_slots'], 'has_route': result['route'] is not None,
            'reason_codes': result['reason_codes']}, 'matches': matches})
    total = len(cases)
    return {
        'evaluation_version': 'intent-evaluation@1',
        'case_count': total,
        'metrics': {
            'decision_accuracy': counts['decision'] / total,
            'intent_accuracy': counts['intent'] / total,
            'missing_slots_exact_accuracy': counts['missing_slots'] / total,
            'route_accuracy': counts['route'] / total,
            'rejection_precision': true_rejects / actual_rejects if actual_rejects else None,
            'rejection_recall': true_rejects / expected_rejects if expected_rejects else None,
        },
        'failures': [detail['case_id'] for detail in details if not all(detail['matches'].values())],
        'cases': details,
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--fixture', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args(argv)
    fixture_raw = args.fixture.read_bytes()
    fixture = json.loads(fixture_raw)
    if fixture.get('fixture_version') != 'intent-evaluation@1' or not isinstance(fixture.get('cases'), list):
        raise SystemExit('invalid intent evaluation fixture')
    report = evaluate(fixture['cases'])
    report['fixture_sha256'] = hashlib.sha256(fixture_raw).hexdigest()
    encoded = (json.dumps(report, ensure_ascii=False, indent=2) + '\n').encode()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(encoded)
    print(json.dumps({'case_count': report['case_count'], 'metrics': report['metrics'],
                      'failure_count': len(report['failures'])}, ensure_ascii=False))
    return 0 if not report['failures'] else 1


if __name__ == '__main__':
    sys.exit(main())
