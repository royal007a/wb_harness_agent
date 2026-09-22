"""Validate that semantic/vector retrieval cannot be represented as enabled without its admission evidence."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from jsonschema import Draft202012Validator


ROOT = Path(__file__).resolve().parents[1]
SCHEMA = json.loads((ROOT / 'specs/v1/memory-semantic-admission.schema.json').read_text())
STATE = ROOT / 'harness/semantic-retrieval-admission.json'


def validate(path=STATE):
    value = json.loads(Path(path).read_text())
    errors = list(Draft202012Validator(SCHEMA).iter_errors(value))
    if errors:
        raise ValueError('; '.join(error.message for error in errors))
    if value['status'] == 'not_admitted':
        assert value['enabled'] is False
        assert value['model_calls'] == 0 and value['external_calls'] == 0
        assert value['admission_evidence'] is None
        assert value['blockers']
    return value


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--path', type=Path, default=STATE)
    parser.add_argument('--json', action='store_true')
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    try:
        value = validate(args.path)
    except (AssertionError, ValueError, json.JSONDecodeError) as exc:
        print(f'semantic retrieval admission: failed: {exc}', file=sys.stderr)
        raise SystemExit(1) from None
    encoded = json.dumps(value, ensure_ascii=False, indent=2) + '\n'
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(encoded)
    if args.json:
        print(encoded, end='')
    elif not args.output:
        print(f"semantic retrieval admission: {value['status']}; enabled={value['enabled']}")


if __name__ == '__main__':
    main()
