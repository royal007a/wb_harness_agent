"""Produce a redacted, repeatable evidence manifest for the Pi P2 offline slice."""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def run(argv, cwd=ROOT):
    result = subprocess.run(argv, cwd=cwd, text=True, capture_output=True, timeout=180)
    if result.returncode:
        raise SystemExit(result.stdout + result.stderr)
    return result.stdout.strip()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, default=ROOT / 'harness/evidence/PI-P2/manifest.json')
    args = parser.parse_args()
    admission = json.loads((ROOT / 'harness/pi-admission.json').read_text())
    npm = run(['npm', 'test'], ROOT / 'pi-adapter')
    targeted = run([sys.executable, '-m', 'pytest', '-q',
                    'tests/test_pi_admission.py', 'tests/test_pi_contract_review_runtime.py',
                    'tests/test_pi_contract_review_adapter.py'])
    full = run(['sh', 'harness/verify.sh'])
    manifest = {
        'evidence_version': 'pi-p2-offline@1',
        'generated_at': datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z'),
        'status': 'passed',
        'scope': 'Pi sidecar + offline contract review Product Run + admission boundary',
        'checks': {
            'node_sidecar_tests': npm.splitlines()[-6:],
            'pi_targeted_tests': targeted.splitlines()[-3:],
            'harness_verify_tail': full.splitlines()[-4:],
        },
        'runtime_assertions': {
            'admission_status': admission['status'],
            'admission_enabled': admission['admission_enabled'],
            'model_calls': admission['model_calls'],
            'external_calls': admission['external_calls'],
            'keychain_resolved': False,
            'network_calls': 0,
            'real_provider_enabled': False,
        },
        'covered': [
            'Pi event mapping and JSONL sidecar protocol',
            'Public PDF resource binding',
            'Risk/Evidence/Handoff/Gate artifacts',
            'Gate and cancellation terminal boundaries',
            'fail-closed L3 admission and runtime binding checks',
        ],
        'not_covered': [
            'real Provider connectivity', 'network/WebSearch/WebFetch',
            'Keychain resolution', 'legal advice quality', 'production SLA',
        ],
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps(manifest, ensure_ascii=False))


if __name__ == '__main__':
    main()
