"""Deterministic stdlib helper. Explicit paths; no network, models or subprocesses."""
import argparse
import csv
from decimal import Decimal, InvalidOperation, localcontext
import hashlib
import io
import json
import os
from pathlib import Path
import sys
import tempfile


def aggregate(raw, group_by, metric, operation):
    if operation not in {'sum', 'mean', 'min', 'max', 'count'}:
        raise ValueError('unsupported operation')
    if not 0 < len(raw) <= 2 * 1024 * 1024:
        raise ValueError('input must be 1 byte to 2 MiB')
    reader = csv.DictReader(io.StringIO(raw.decode('utf-8-sig')), strict=True)
    headers = reader.fieldnames
    if not headers or len(headers) > 100 or len(set(headers)) != len(headers):
        raise ValueError('invalid or duplicate headers')
    if group_by not in headers or metric not in headers or group_by == metric:
        raise ValueError('select distinct existing group and metric columns')
    groups, rows, missing = {}, 0, 0
    for row in reader:
        rows += 1
        if rows > 20000 or None in row or any(v is None for v in row.values()):
            raise ValueError('row limit or shape mismatch')
        group = row[group_by]
        if not group.strip() or len(group) > 256:
            raise ValueError('invalid group label')
        values = groups.setdefault(group, [])
        if len(groups) > 50:
            raise ValueError('group limit exceeded')
        value = row[metric].strip()
        if not value:
            missing += 1
            continue
        if len(value) > 64:
            raise ValueError('numeric value too long')
        number = Decimal(value)
        if not number.is_finite() or abs(number.adjusted()) > 100:
            raise ValueError('numeric value is non-finite or out of range')
        values.append(number)
    if not rows:
        raise ValueError('empty table')
    output = []
    with localcontext() as context:
        context.prec = 256
        for group, values in sorted(groups.items()):
            if operation == 'count':
                value = Decimal(len(values))
            elif not values:
                value = None
            elif operation == 'sum':
                value = sum(values, Decimal(0))
            elif operation == 'mean':
                value = sum(values, Decimal(0)) / len(values)
            else:
                value = min(values) if operation == 'min' else max(values)
            output.append({'group': group, 'value': format(value, 'f') if value is not None else None,
                           'valid_count': len(values)})
    return {'schema_version': '1.0', 'input_sha256': hashlib.sha256(raw).hexdigest(),
            'group_by': group_by, 'metric': metric, 'operation': operation,
            'row_count': rows, 'missing_values': missing, 'values': output}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--group-by', required=True)
    parser.add_argument('--metric', required=True)
    parser.add_argument('--operation', required=True, choices=['sum', 'mean', 'min', 'max', 'count'])
    args = parser.parse_args()
    temporary = None
    try:
        with args.input.open('rb') as source:
            raw = source.read(2 * 1024 * 1024 + 1)
        result = aggregate(raw, args.group_by, args.metric, args.operation)
        encoded = (json.dumps(result, ensure_ascii=False, allow_nan=False) + '\n').encode()
        # Publish atomically and refuse overwrite, including symlinks. Parent
        # directory must already be provisioned by the authorized caller.
        with tempfile.NamedTemporaryFile(dir=args.output.parent, delete=False) as target:
            temporary = Path(target.name)
            target.write(encoded)
            target.flush()
            os.fsync(target.fileno())
        os.link(temporary, args.output)
        print(json.dumps({'status': 'ok', 'path': str(args.output), 'sha256': hashlib.sha256(encoded).hexdigest(),
                          'row_count': result['row_count'], 'group_count': len(result['values'])}))
        return 0
    except (OSError, ValueError, InvalidOperation, csv.Error):
        print(json.dumps({'status': 'error', 'code': 'INVALID_INPUT_OR_OUTPUT',
                          'message': 'Check CSV, column names, numeric values and unused output path.'}))
        return 1
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


if __name__ == '__main__':
    sys.exit(main())
