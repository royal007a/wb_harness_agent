"""HA-0083 targeted in-memory mutations; never edit the checked-out runtime source."""
import argparse
import json
from pathlib import Path
import subprocess
import sys
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
CASES = {
    'reexecute_completed': (
        "return copy.deepcopy(self.responses[ident])", "item = dict(item, status='issued')",
        'test_replay_exact_mutation_safe_and_no_writes'),
    'ignore_request_binding': (
        "if item['request_sha256'] is not None and sha != item['request_sha256']:",
        "if False:", 'test_conflict_or_forged_identity_never_executes'),
    'replay_after_cancel': (
        'self.check()  # Includes cancellation/deadline, also before serving a cached receipt.',
        'pass  # mutant: no pre-replay cancellation check', 'test_cancel_prevents_replay_without_duplicate_action'),
    'reuse_provider_id': (
        "ticket = 't_' + str(turn) + '_' + str(ordinal) + '_' + uuid.uuid4().hex",
        "ticket = call['id']", 'test_same_raw_id_and_arguments_next_round_is_new_action'),
    'forget_unknown': (
        "status = 'unknown' if row['status'] == 'in_flight' else 'failed'",
        "status = 'failed'", 'test_restart_retains_unknown_and_never_resends'),
    'skip_predecessor': (
        "if kind == 'model' and any(", "if False and any(",
        'test_same_raw_id_and_arguments_next_round_is_new_action'),
    'omit_audit': (
        'self._event(db, item)', 'pass  # mutant: no audit', 'test_receipt_event_atomicity_before_action'),
}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--case', choices=CASES)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    if args.case:
        import pytest
        import backend.dsh_crossings as module
        import backend.dsh_runtime as runtime
        old, new, selector = CASES[args.case]
        source = (ROOT / 'backend/dsh_crossings.py').read_text()
        assert old in source
        exec(compile(source.replace(old, new), str(ROOT / 'backend/dsh_crossings.py'), 'exec'), module.__dict__)
        runtime.Crossings = module.Crossings
        runtime.retire_crossings = module.retire
        return pytest.main(['-q', 'tests/test_dsh_crossings.py', '-k', selector,
                            '--junitxml=' + str(args.out / (args.case + '.xml'))])
    results = []
    for name in CASES:
        proc = subprocess.run([sys.executable, __file__, '--case', name, '--out', str(args.out)],
                              cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        (args.out / (name + '.log')).write_text(proc.stdout)
        xml = ET.parse(args.out / (name + '.xml'))
        failures = len(xml.findall('.//failure'))
        errors = len(xml.findall('.//error'))
        results.append(dict(name=name, exit_code=proc.returncode, failures=failures, errors=errors,
                            killed=proc.returncode == 1 and failures > 0 and errors == 0))
    (args.out / 'results.json').write_text(json.dumps(results, indent=2) + '\n')
    print(json.dumps(results, indent=2))
    return 0 if all(row['killed'] for row in results) else 1


if __name__ == '__main__':
    raise SystemExit(main())
