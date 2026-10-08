"""Read-only consistency validation. No network, shell execution, or deployment."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import sys
from urllib.parse import urlsplit


class Invalid(ValueError):
    pass


def require(condition, message):
    if not condition:
        raise Invalid(message)


def canonical(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(',', ':'), allow_nan=False)


def digest(plan):
    return hashlib.sha256(canonical(plan).encode()).hexdigest()


def load(path):
    def unique(pairs):
        result = {}
        for key, value in pairs:
            require(key not in result, 'duplicate JSON key')
            result[key] = value
        return result
    def invalid_number(value):
        raise Invalid('non-finite JSON number')
    return json.loads(Path(path).read_text(), object_pairs_hook=unique, parse_constant=invalid_number)


def obj(value, required, optional=()):
    require(isinstance(value, dict), 'object required')
    require(set(required) <= value.keys(), 'missing object fields')
    require(value.keys() <= set(required) | set(optional), 'unknown object fields')


def nonempty(value):
    return isinstance(value, str) and bool(value.strip())


def identifier(value):
    require(isinstance(value, str) and re.fullmatch(r'[a-zA-Z0-9_-]{1,80}', value), 'invalid identifier')


def validate_plan(plan):
    obj(plan, {'schema', 'targets'})
    require(plan['schema'] == 'deployment-plan@1', 'unsupported plan schema')
    require(isinstance(plan['targets'], list) and plan['targets'], 'targets required')
    targets = {}
    for target in plan['targets']:
        obj(target, {'id', 'release', 'data_path', 'public_entry', 'checks'})
        identifier(target['id'])
        require(target['id'] not in targets, 'duplicate target')
        require(nonempty(target['release']), 'fixed release required')
        require(target['data_path'] is None or nonempty(target['data_path']), 'invalid data path')
        require(isinstance(target['checks'], list), 'checks must be a list')
        checks = {}
        for check in target['checks']:
            obj(check, {'id', 'required', 'expected'}, {'kind'})
            identifier(check['id'])
            require(check['id'] not in checks, 'duplicate check')
            require(type(check['required']) is bool, 'required must be boolean')
            require(isinstance(check['expected'], dict) and check['expected'], 'expected values required')
            require(check.get('kind', 'check') in {'check', 'command'}, 'unsupported check kind')
            checks[check['id']] = check
        for key in ['release', 'identity', 'health']:
            require(key in checks and checks[key]['required'], 'missing required core check: ' + key)
        require(checks['release']['expected'].get('release') == target['release'], 'release check must bind target release')
        require(checks['identity']['expected'].get('identity_stable') is True, 'identity check must require stable identity')
        entry = target['public_entry']
        if entry is None:
            require('public_entry' not in checks, 'public_entry check reserved for a declared public entry')
        else:
            obj(entry, {'url', 'tls'}, {'exception_reason'})
            require(nonempty(entry['url']), 'public URL required')
            parsed = urlsplit(entry['url'])
            require(parsed.scheme in {'http', 'https'} and parsed.hostname and parsed.username is None and parsed.password is None and not parsed.fragment, 'invalid public URL')
            if parsed.scheme == 'https':
                require(entry['tls'] in {'verified', 'existing_exception'}, 'HTTPS TLS policy required')
                if entry['tls'] == 'existing_exception':
                    require(nonempty(entry.get('exception_reason')), 'TLS exception reason required')
            else:
                require(entry['tls'] == 'not_applicable', 'HTTP TLS policy must be not_applicable')
            expected = {'url': entry['url'], 'transport': 'direct', 'tls': entry['tls']}
            require('public_entry' in checks and checks['public_entry']['required'], 'public entry must be required')
            require(all(checks['public_entry']['expected'].get(k) == v for k, v in expected.items()), 'public check changed planned transport or URL')
            outcome = checks['public_entry']['expected']
            code = outcome.get('http_status')
            require(type(code) is int and 200 <= code < 300, 'public check requires successful integer HTTP status')
            require(outcome.get('application_ok') is True, 'public check requires application_ok=true')
        if target['data_path'] is not None:
            for key in ['backup', 'preservation']:
                require(key in checks and checks[key]['required'], 'persistent target missing ' + key)
            expected = checks['backup']['expected']
            require(expected.get('database') == target['data_path'] and expected.get('integrity') == 'ok', 'backup must bind actual database and integrity')
        targets[target['id']] = (target, checks)
    return targets


def check_evidence(items, root):
    require(isinstance(items, list), 'evidence must be a list')
    for item in items:
        obj(item, {'path', 'sha256'})
        require(nonempty(item['path']), 'evidence path required')
        path = Path(item['path'])
        require(not path.is_absolute() and '..' not in path.parts, 'unsafe evidence path')
        path = (root / path).resolve()
        require(path.is_relative_to(root) and path.is_file(), 'evidence must be a file inside evidence root')
        require(isinstance(item['sha256'], str) and re.fullmatch('[a-f0-9]{64}', item['sha256']), 'invalid evidence digest')
        h = hashlib.sha256()
        with path.open('rb') as source:
            for chunk in iter(lambda: source.read(65536), b''):
                h.update(chunk)
        require(h.hexdigest() == item['sha256'], 'evidence digest mismatch')


def verify(plan, receipt, evidence_root):
    targets = validate_plan(plan)
    obj(receipt, {'schema', 'plan_sha256', 'targets'})
    require(receipt['schema'] == 'deployment-receipt@1', 'unsupported receipt schema')
    require(receipt['plan_sha256'] == digest(plan), 'receipt does not bind fixed plan')
    require(isinstance(receipt['targets'], list), 'receipt targets must be a list')
    records = {}
    for record in receipt['targets']:
        obj(record, {'id', 'deployment_status', 'checks'})
        require(record['id'] in targets and record['id'] not in records, 'unknown or duplicate receipt target')
        require(record['deployment_status'] in {'deployed', 'failed', 'not_attempted'}, 'invalid deployment status')
        require(isinstance(record['checks'], dict), 'check results must be an object')
        require(record['checks'].keys() <= targets[record['id']][1].keys(), 'unplanned check result')
        records[record['id']] = record
    root = Path(evidence_root).resolve()
    require(root.is_dir(), 'evidence root missing')
    output = []
    for ident, (target, checks) in targets.items():
        record = records.get(ident, {'deployment_status': 'not_attempted', 'checks': {}})
        results, limitations, prior_failures = {}, [], 0
        for key, spec in checks.items():
            item = record['checks'].get(key)
            attempts = []
            if item is not None:
                obj(item, {'attempts'})
                attempts = item['attempts']
                require(isinstance(attempts, list) and attempts, 'attempts must be a nonempty list')
            statuses = []
            for attempt in attempts:
                obj(attempt, {'status', 'observed', 'evidence'}, {'reason'})
                status = attempt['status']
                require(status in {'pass', 'fail', 'skipped', 'not_run'}, 'invalid attempt status')
                require(isinstance(attempt['observed'], dict), 'observed must be an object')
                if status != 'pass':
                    require(nonempty(attempt.get('reason')), 'non-pass reason required')
                check_evidence(attempt['evidence'], root)
                if status in {'pass', 'fail'}:
                    require(bool(attempt['evidence']), 'executed check needs evidence')
                if status == 'pass':
                    matches = all(k in attempt['observed'] and canonical(attempt['observed'][k]) == canonical(v) for k, v in spec['expected'].items())
                    if spec.get('kind') == 'command':
                        code = attempt['observed'].get('exit_code')
                        matches = matches and type(code) is int and code == 0
                    if not matches:
                        status = 'fail'
                statuses.append(status)
            prior_failures += statuses[:-1].count('fail')
            results[key] = statuses[-1] if statuses else 'not_run'
            if not spec['required'] and results[key] != 'pass':
                limitations.append('optional check not passed: ' + key)
        needed = [results[k] for k, v in checks.items() if v['required']]
        if record['deployment_status'] == 'failed' or 'fail' in needed:
            state = 'failed'
        elif record['deployment_status'] != 'deployed' or any(v != 'pass' for v in needed):
            state = 'incomplete'
        else:
            state = 'verified'
        entry = target['public_entry']
        if entry and entry['tls'] == 'existing_exception':
            limitations.append('TLS exception: ' + entry['exception_reason'])
        if state == 'verified' and limitations:
            state = 'verified_with_exceptions'
        output.append({'id': ident, 'reported_deployment_status': record['deployment_status'], 'verification': state,
                       'public_entry_required': entry is not None, 'checks': results, 'prior_failed_attempts': prior_failures, 'limitations': limitations})
    states = [r['verification'] for r in output]
    overall = 'failed' if 'failed' in states else 'incomplete' if 'incomplete' in states else 'verified_with_exceptions' if 'verified_with_exceptions' in states else 'verified'
    return {'verification': overall, 'plan_sha256': digest(plan), 'targets': output, 'scope': 'local consistency only; external facts not independently verified'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('plan'); parser.add_argument('receipt', nargs='?')
    parser.add_argument('--evidence-root', default='.'); parser.add_argument('--digest', action='store_true')
    parser.add_argument('--expected-plan-sha256', help='Compare with a digest registered before deployment')
    args = parser.parse_args()
    try:
        plan = load(args.plan)
        validate_plan(plan)
        if args.expected_plan_sha256 is not None:
            require(args.expected_plan_sha256 == digest(plan), 'plan does not match preregistered digest')
        if args.digest:
            print(digest(plan)); return 0
        require(args.receipt is not None, 'receipt path required')
        result = verify(plan, load(args.receipt), args.evidence_root)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0 if result['verification'].startswith('verified') else 1
    except (Invalid, OSError, ValueError, TypeError, KeyError, RecursionError) as exc:
        print(json.dumps({'verification': 'invalid', 'error_type': type(exc).__name__, 'message': str(exc) if isinstance(exc, Invalid) else 'Invalid contract or evidence; inspect inputs locally.'}), file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
