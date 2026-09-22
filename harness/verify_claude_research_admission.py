"""Validate the Native Claude L3 admission profile without touching external systems."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.claude_research_admission import ADMISSION_STATE, runtime_status, validate


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--path', type=Path, default=ADMISSION_STATE)
    parser.add_argument('--json', action='store_true')
    args = parser.parse_args()
    try:
        value = validate(json.loads(args.path.read_text()))
    except Exception as exc:
        raise SystemExit(f'claude research admission: failed: {exc}') from None
    status = runtime_status(args.path)
    if args.json:
        print(json.dumps({'profile': value, 'runtime': status}, ensure_ascii=False, indent=2))
    else:
        print(f"claude research admission: {value['status']}; enabled={value['admission_enabled']}")


if __name__ == '__main__':
    main()
