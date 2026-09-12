"""Opt-in Colima/SDK checks. Run from repository root with the project venv."""
from datetime import datetime, timezone
from importlib.metadata import version
import json
import os
from pathlib import Path
import subprocess
import sys
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from backend.sandbox import image_id, profile_digest


def main():
    directory = ROOT / 'harness/evidence/HA-0007'
    directory.mkdir(parents=True, exist_ok=True)
    image, profile, sdk = image_id(), profile_digest(), version('smolagents')
    result = subprocess.run([sys.executable, '-m', 'pytest', 'tests/test_sandbox.py', 'tests/test_skill_script.py',
                             '-q', '--junitxml=' + str(directory / 'probe-tests.xml')], cwd=ROOT,
                            env={**os.environ, 'HARNESS_DOCKER_TESTS': '1'}, timeout=180, check=False)
    suite = ET.parse(directory / 'probe-tests.xml').getroot().find('testsuite')
    counts = {key: int(suite.attrib[key]) for key in ('tests', 'failures', 'errors', 'skipped')}
    passed = result.returncode == 0 and counts['tests'] >= 23 and not any(counts[k] for k in ('failures','errors','skipped'))
    passed = passed and image == image_id() and profile == profile_digest() and sdk == version('smolagents')
    report = {'status': 'passed' if passed else 'failed', 'checked_at': datetime.now(timezone.utc).isoformat(),
              'profile_sha256': profile, 'image_id': image, 'smolagents_version': sdk,
              'mode': 'scripted_model_real_sdk_real_vm', 'real_model': False, 'tests': counts,
              'limitations': ['no model provider called', 'no natural-language quality evaluation',
                              'no production sandbox certification', 'SDK route stays disabled']}
    (directory / 'probe.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report))
    return 0 if passed else 1


if __name__ == '__main__':
    sys.exit(main())
