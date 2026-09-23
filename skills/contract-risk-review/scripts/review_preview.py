#!/usr/bin/env python3
"""Create deterministic, human-gated candidate findings from a pipeline preview."""
from __future__ import annotations

import argparse
import json
import sys


def review(preview: dict) -> dict:
    if preview.get('schema_version') != 'pi-contract-pipeline-preview@1':
        raise ValueError('unsupported preview schema')
    resource_id = preview.get('resource_id', '')
    if not resource_id.startswith('res_'):
        raise ValueError('invalid resource id')
    chunks = preview.get('chunks') or []
    refs = [f"evidence://{resource_id}/chunk-{item['index']}/{item['text_sha256']}" for item in chunks]
    focus = preview.get('classification', {}).get('focus_areas', [])
    security = preview.get('security', {})
    if security.get('status') != 'clear':
        recommendation = '先完成敏感信息人工复核，再决定是否继续合同审查。'
        level = 'high'
    else:
        recommendation = '逐项核对关注领域并由法务/业务负责人确认，不能据此单独签署或拒签。'
        level = 'medium' if focus else 'low'
    return {
        'schema_version': 'contract-risk-review-candidate@1',
        'status': 'needs_human',
        'risk_level': level,
        'source_resource_id': resource_id,
        'source_sha256': preview.get('source_sha256'),
        'method': 'deterministic_skill_baseline@1',
        'focus_areas': focus,
        'evidence_refs': refs,
        'recommendation': recommendation,
        'model_calls': 0,
        'external_calls': 0,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('preview', nargs='?', default='-')
    args = parser.parse_args()
    source = sys.stdin if args.preview == '-' else open(args.preview, encoding='utf-8')
    with source:
        value = json.load(source)
    result = review(value)
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
