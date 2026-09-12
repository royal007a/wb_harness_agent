import hashlib
import json
from pathlib import Path
import subprocess
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / 'skills/csv-group-analysis/scripts/aggregate.py'


def run(tmp_path, raw, operation='sum'):
    source, output = tmp_path / 'input.csv', tmp_path / 'result.json'
    source.write_bytes(raw)
    process = subprocess.run([sys.executable, str(SCRIPT), '--input', str(source), '--output', str(output),
                              '--group-by', 'region', '--metric', 'revenue', '--operation', operation],
                             capture_output=True, timeout=5)
    return process, output


@pytest.mark.parametrize('operation,expected', [('sum','0.3'), ('mean','0.15'), ('min','0.1'), ('max','0.2'), ('count','2')])
def test_exact_decimal_and_reference(tmp_path, operation, expected):
    raw = b'region,revenue\nEast,0.1\nEast,0.2\nEast,\n'
    process, output = run(tmp_path, raw, operation)
    assert process.returncode == 0, process.stderr
    ref = json.loads(process.stdout)
    assert 'values' not in ref
    result = json.loads(output.read_bytes())
    assert result['values'] == [{'group': 'East', 'value': expected, 'valid_count': 2}]
    assert result['missing_values'] == 1
    assert result['input_sha256'] == hashlib.sha256(raw).hexdigest()
    assert ref['sha256'] == hashlib.sha256(output.read_bytes()).hexdigest()


@pytest.mark.parametrize('raw', [b'region,revenue\n', b'region,revenue\nA,NaN\n', b'region,revenue\nA,bad\n',
                               b'region,region\nA,1\n', b'region,revenue\nA,1,2\n',
                               b'region,revenue\nA,1e9999\n'])
def test_reject_invalid_without_artifact(tmp_path, raw):
    process, output = run(tmp_path, raw)
    assert process.returncode == 1 and json.loads(process.stdout)['status'] == 'error'
    assert not output.exists()


def test_refuse_overwrite(tmp_path):
    output = tmp_path / 'result.json'
    output.write_text('existing user artifact')
    process, _ = run(tmp_path, b'region,revenue\nA,1\n')
    assert process.returncode == 1 and output.read_text() == 'existing user artifact'
    assert sorted(p.name for p in tmp_path.iterdir()) == ['input.csv', 'result.json']
