"""Paired heading-only variant; original fixtures/labels are never rewritten."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
from harness.dsh_payment_eval import EVAL, run_case, score


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--out', required=True)
    args = parser.parse_args()
    source = (EVAL / 'cases.json').read_bytes()
    cases = json.loads(source)['cases']
    # Fixed corpus currently contains headings 1..14. Fail if this premise changes.
    names = ('', '一', '二', '三', '四', '五', '六', '七', '八', '九', '十', '十一', '十二', '十三', '十四')
    replacements = 0
    def rename(match):
        nonlocal replacements
        index = int(match[1])
        if not 1 <= index < len(names):
            raise ValueError('unmapped corpus heading')
        replacements += 1
        return '第' + names[index] + '条'
    for case in cases:
        case['document'] = re.sub(r'^第([0-9]+)条', rename, case['document'], flags=re.M)
    assert replacements > 0
    dataset_sha = hashlib.sha256(json.dumps(cases, ensure_ascii=False, sort_keys=True).encode()).hexdigest()
    results = []
    with tempfile.TemporaryDirectory() as tmp:
        for case in cases:
            path = Path(tmp).resolve() / case['id']
            path.mkdir()
            results.append(run_case(case, path))
    # Not available to scripted Provider; read only after every case finishes.
    labels_bytes = (EVAL / 'labels.json').read_bytes()
    rows, metrics = score(results, json.loads(labels_bytes)['labels'])
    result = {'eval': 'dsh-payment-chinese-headings@1',
              'scoring_version': 'fixed-script-value-unit@2', 'cases': len(cases),
              'source_cases_sha256': hashlib.sha256(source).hexdigest(),
              'dataset_sha256': dataset_sha, 'labels_sha256': hashlib.sha256(labels_bytes).hexdigest(),
              'heading_replacements': replacements,
              'provider': 'synthetic scripted (label-blind)',
              'not_evidence': ['real model quality', 'production deployment', 'arbitrary Chinese legal numbering'],
              'metrics': metrics, 'rows': rows,
              'model_calls_total': sum(r['model_calls'] for r in rows)}
    Path(args.out).write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps({'cases': len(cases), 'metrics': metrics}, ensure_ascii=False))


if __name__ == '__main__':
    main()
