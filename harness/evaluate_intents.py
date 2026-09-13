"""Score redacted intent-routing candidates without invoking a model."""
import argparse
import hashlib
import json
from pathlib import Path
import sys

from jsonschema import Draft202012Validator


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.intent import IntentRouter


EVALUATION_CONTRACT = json.loads((ROOT / 'specs/v1/intent-evaluation.schema.json').read_text())


def _validate(kind, value):
    schema = {'$ref': '#/$defs/' + kind, '$defs': EVALUATION_CONTRACT['$defs']}
    errors = list(Draft202012Validator(schema).iter_errors(value))
    if errors:
        paths = ', '.join('/'.join(str(part) for part in error.path) or '$' for error in errors[:3])
        raise ValueError('invalid {} at {}'.format(kind, paths))


def _validate_fixture(fixture):
    version = fixture.get('fixture_version') if isinstance(fixture, dict) else None
    if version == 'intent-evaluation@1':
        if not isinstance(fixture.get('cases'), list):
            raise ValueError('invalid intent-evaluation@1 fixture')
    elif version == 'intent-evaluation@2':
        _validate('fixture', fixture)
    else:
        raise ValueError('unsupported intent evaluation fixture version')
    case_ids = [case.get('id') for case in fixture['cases']]
    if len(case_ids) != len(set(case_ids)):
        raise ValueError('fixture contains duplicate case IDs')
    return version


def _rules_predictions(cases):
    router = IntentRouter()
    predictions = []
    for case in cases:
        request = case['request']
        resource = {'id': 'res_fixture'} if request['has_resource'] else None
        result = router.interpret(
            {'objective': request['objective'], **({'resource_id': resource['id']} if resource else {})},
            resource,
        )
        predictions.append({
            'case_id': case['id'],
            'decision': result['decision'],
            'intent_id': result['intent']['id'] if result['intent'] else None,
            'missing_slots': result['missing_slots'],
            'has_route': result['route'] is not None,
            'reason_codes': result['reason_codes'],
        })
    return predictions


def _validate_candidate(candidate, fixture_sha256, case_ids):
    _validate('candidate_output', candidate)
    if candidate['fixture_sha256'] != fixture_sha256:
        raise ValueError('candidate fixture SHA-256 does not match')
    by_id = {}
    for prediction in candidate['predictions']:
        case_id = prediction['case_id']
        if case_id in by_id:
            raise ValueError('candidate contains duplicate case IDs')
        by_id[case_id] = prediction
    expected_ids = set(case_ids)
    if set(by_id) != expected_ids:
        raise ValueError('candidate case IDs do not exactly match fixture')
    return [by_id[case_id] for case_id in case_ids]


def _score(cases, predictions):
    if len(cases) != len(predictions):
        raise ValueError('prediction count does not match cases')
    details = []
    expected_rejects = actual_rejects = true_rejects = 0
    counts = {'decision': 0, 'intent': 0, 'missing_slots': 0, 'route': 0}
    for case, prediction in zip(cases, predictions):
        expected = case['expected']
        actual = {
            'decision': prediction['decision'],
            'intent_id': prediction['intent_id'],
            'missing_slots': prediction['missing_slots'],
            'has_route': prediction['has_route'],
        }
        matches = {
            'decision': actual['decision'] == expected['decision'],
            'intent': actual['intent_id'] == expected['intent_id'],
            'missing_slots': actual['missing_slots'] == expected['missing_slots'],
            'route': actual['has_route'] == expected['has_route'],
        }
        for name, matched in matches.items():
            counts[name] += int(matched)
        expected_rejects += int(expected['decision'] == 'rejected')
        actual_rejects += int(actual['decision'] == 'rejected')
        true_rejects += int(expected['decision'] == actual['decision'] == 'rejected')
        details.append({
            'case_id': case['id'],
            'actual': actual,
            'matches': matches,
        })
    total = len(cases)
    return {
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


def _category_counts(cases):
    counts = {}
    for case in cases:
        category = case.get('category')
        if category:
            counts[category] = counts.get(category, 0) + 1
    return counts


def _evaluate_policy(policy, fixture_version, report, candidate):
    _validate('policy', policy)
    failures = []
    if fixture_version != policy['fixture_version']:
        failures.append('fixture_version_mismatch')
    if report['case_count'] < policy['minimum_case_count']:
        failures.append('case_count_below_minimum')
    for category, minimum in policy['required_category_counts'].items():
        if report['category_counts'].get(category, 0) < minimum:
            failures.append('category_{}_below_minimum'.format(category))
    if candidate['candidate']['execution_mode'] != policy['required_execution_mode']:
        failures.append('execution_mode_mismatch')
    for metric, minimum in policy['minimum_metrics'].items():
        actual = report['metrics'][metric]
        if actual is None or actual < minimum:
            failures.append('metric_{}_below_minimum'.format(metric))
    return {
        'policy_version': policy['policy_version'],
        'eligible_for_next_shadow_stage': not failures,
        'failures': failures,
    }


def evaluate(fixture, fixture_sha256, candidate=None, policy=None):
    fixture_version = _validate_fixture(fixture)
    cases = fixture['cases']
    case_ids = [case['id'] for case in cases]
    if candidate is None:
        predictions = _rules_predictions(cases)
        candidate_summary = {'kind': 'rules_baseline', 'version': 'rules@1', 'execution_mode': 'local'}
    else:
        if fixture_version != 'intent-evaluation@2':
            raise ValueError('shadow candidates require intent-evaluation@2')
        predictions = _validate_candidate(candidate, fixture_sha256, case_ids)
        candidate_summary = {
            'kind': candidate['candidate']['kind'],
            'execution_mode': candidate['candidate']['execution_mode'],
            'provider_ref': candidate['candidate']['provider_ref'],
            'model_ref': candidate['candidate']['model_ref'],
            'input_classification': candidate['execution']['input_classification'],
            'prompt_template_sha256': candidate['execution']['prompt_template_sha256'],
            'tool_call_count': candidate['execution']['tool_call_count'],
            'model_call_count': candidate['execution']['model_call_count'],
        }
    report = {
        'evaluation_version': fixture_version,
        'score_version': 'intent-score@2',
        'case_count': len(cases),
        'category_counts': _category_counts(cases),
        'candidate': candidate_summary,
        **_score(cases, predictions),
        'fixture_sha256': fixture_sha256,
    }
    if policy is not None:
        if candidate is None:
            raise ValueError('a policy can only evaluate a shadow candidate output')
        report['policy'] = _evaluate_policy(policy, fixture_version, report, candidate)
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--fixture', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--candidate-output', type=Path)
    parser.add_argument('--policy', type=Path)
    parser.add_argument('--allow-mismatch', action='store_true',
                        help='write a diagnostic baseline report even when predictions differ')
    parser.add_argument('--enforce-policy', action='store_true',
                        help='exit nonzero when a supplied policy does not qualify the shadow candidate')
    args = parser.parse_args(argv)
    if args.enforce_policy and args.policy is None:
        parser.error('--enforce-policy requires --policy')
    try:
        fixture_raw = args.fixture.read_bytes()
        fixture = json.loads(fixture_raw)
        fixture_sha256 = hashlib.sha256(fixture_raw).hexdigest()
        candidate = json.loads(args.candidate_output.read_text()) if args.candidate_output else None
        policy = json.loads(args.policy.read_text()) if args.policy else None
        report = evaluate(fixture, fixture_sha256, candidate, policy)
    except (OSError, json.JSONDecodeError, ValueError) as error:
        print('intent evaluation error: {}'.format(error), file=sys.stderr)
        return 2
    encoded = (json.dumps(report, ensure_ascii=False, indent=2) + '\n').encode()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(encoded)
    print(json.dumps({
        'case_count': report['case_count'],
        'metrics': report['metrics'],
        'failure_count': len(report['failures']),
        'policy_eligible': report.get('policy', {}).get('eligible_for_next_shadow_stage'),
    }, ensure_ascii=False))
    has_policy_failure = args.enforce_policy and not report.get('policy', {}).get('eligible_for_next_shadow_stage', False)
    return 1 if (has_policy_failure or (report['failures'] and not args.allow_mismatch)) else 0


if __name__ == '__main__':
    sys.exit(main())
