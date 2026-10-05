"""Run fixed HA-0078 mutations in disposable Python processes, never edit runtime files.

Only trusted, checked-in source is compiled. There is no model-generated code or
user-provided replacement. Each pytest process uses temporary DBs and synthetic
Providers. This is a targeted regression check, not a repository mutation score.
"""
import hashlib
import importlib
import json
from pathlib import Path
import subprocess
import sys
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
CASES = [
    ('model_cap', 'backend.dsh_runtime', "counts['model_calls'] >= 8", "counts['model_calls'] >= 9",
     'test_sdk_exact_model_call_cap'),
    ('tool_cap', 'backend.dsh_runtime', "counts['tool_calls'] >= 16", "counts['tool_calls'] >= 17",
     'test_sdk_exact_tool_call_cap'),
    ('late_publish', 'backend.dsh_runtime',
     'with self.store.transaction() as db:\n                check()\n                current =',
     'with self.store.transaction() as db:\n                current =',
     'test_platform_cancel_after_adapter_result_before_publish'),
    ('encoding', 'backend.dsh_provider', "if 'content-encoding' in response.headers:",
     "if False:", 'test_http_fixed_route_no_retry_no_decode_and_limits'),
    ('reservation_equality', 'backend.business_budget',
     "['remaining'] < input_bound + output_limit:", "['remaining'] <= input_bound + output_limit:",
     'test_platform_second_call_reservation_exact_boundary'),
    ('claim', 'backend.dsh_runtime', "if run['status'] != 'queued':", "if run['status'] in TERMINAL:",
     'test_sdk_concurrent_execute_claims_once'),
    ('journal_identity', 'adapters.dsh_workspace',
     '(info.st_dev, info.st_ino) != (record[\'device\'], record[\'inode\'])',
     'False', 'test_cleanup_rejects_corrupt_journal_without_touching_content'),
]


def child(index, xml):
    _, module_name, old, new, selector = CASES[index]
    # Load app first so all circular module imports follow normal startup order.
    import backend.app  # noqa: F401
    module = importlib.import_module(module_name)
    path = Path(module.__file__)
    source = path.read_text()
    assert source.count(old) == 1, 'mutation anchor must be unique'
    exec(compile(source.replace(old, new), str(path), 'exec'), module.__dict__)
    import pytest
    return pytest.main(['-q', 'tests/test_dsh_adversarial.py', '-k', selector,
                        '--tb=short', '--junitxml=' + xml])


def main():
    if len(sys.argv) > 1 and sys.argv[1] == '--child':
        return child(int(sys.argv[2]), sys.argv[3])
    output = ROOT / 'harness/evidence/HA-0078'
    output.mkdir(parents=True, exist_ok=True)
    paths = {ROOT / (item[1].replace('.', '/') + '.py') for item in CASES}
    before = {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}
    results = []
    for index, (name, *_) in enumerate(CASES):
        xml = output / ('mutation-' + name + '.xml')
        run = subprocess.run([sys.executable, '-m', 'harness.dsh_validation_mutations',
                              '--child', str(index), str(xml)], cwd=ROOT,
                             capture_output=True, text=True, timeout=90)
        # Keep machine-readable assertions; do not count import/setup failures.
        tree = ET.parse(xml)
        errors = len(tree.findall('.//error'))
        failures = tree.findall('.//failure')
        assertions = all('AssertionError' in (node.text or '') or
                         'assert ' in (node.text or '') or
                         'Failed: DID NOT RAISE' in (node.text or '') for node in failures)
        killed = run.returncode == 1 and bool(failures) and errors == 0 and assertions
        results.append({'name': name, 'returncode': run.returncode, 'failures': len(failures),
                        'errors': errors, 'assertion_failures_only': assertions, 'killed': killed,
                        'xml': str(xml.relative_to(ROOT))})
        print(name, 'killed' if killed else 'NOT VALIDATED', flush=True)
    after = {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}
    assert before == after, 'production files must never change'
    (output / 'mutations.json').write_text(json.dumps({
        'method': 'isolated-process in-memory source mutation; no production file writes',
        'source_sha256': before, 'results': results,
        'not_evidence': 'targeted selectors only; not full-suite mutation score'}, indent=2) + '\n')
    return 0 if all(row['killed'] for row in results) else 1


if __name__ == '__main__':
    raise SystemExit(main())
