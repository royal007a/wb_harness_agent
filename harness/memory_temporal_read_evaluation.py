"""Synthetic deterministic evaluation of as-of visibility across M1/M2 read paths."""
from __future__ import annotations

import argparse
import json
import sys
import tempfile
from pathlib import Path

from fastapi.testclient import TestClient


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.app import create_app  # noqa: E402


CASESET_VERSION = 'memory-temporal-read-safety-synthetic@1'


def request(client, method, path, *, body=None, key=None, expected=(200, 201)):
    response = client.request(method, path, json=body, headers={'Idempotency-Key': key} if key else {})
    if response.status_code not in expected:
        raise RuntimeError(f'{method} {path} -> {response.status_code}: {response.text}')
    return response.json()


def run():
    with tempfile.TemporaryDirectory(prefix='harness-memory-temporal-eval-') as directory:
        with TestClient(create_app(Path(directory) / 'evaluation.db', False), base_url='http://127.0.0.1') as client:
            bank = request(client, 'POST', '/api/local/memory/banks', key='temporal-eval-bank', body={
                'name': 'temporal-evaluation', 'scope': 'project', 'data_classification': 'Internal', 'retention_days': 90,
            })
            stored = request(client, 'POST', f'/api/local/memory/banks/{bank["id"]}/retain', key='temporal-eval-retain', body={
                'source': {'source_ref': 'eval:future', 'content': '合成未来来源正文，不应输出。',
                           'occurred_at': '2026-09-22T10:00:00Z', 'data_classification': 'Internal'},
                'facts': [{
                    'statement': '未来发布决策。', 'kind': 'decision', 'detail': '合成未来详情。', 'confidence': 0.9,
                    'occurred_at': '2026-09-22T10:00:00Z', 'valid_from': '2026-09-22T10:00:00Z',
                    'valid_to': None, 'supersedes_fact_id': None,
                }],
            })
            fact_id = stored['facts'][0]['id']
            before = '2026-09-21T23:59:59Z'
            after = '2026-09-22T10:00:00Z'
            m1_before = request(client, 'POST', f'/api/local/memory/banks/{bank["id"]}:recall', body={'query': '未来发布', 'as_of': before})
            m2_before = request(client, 'POST', f'/api/local/memory/banks/{bank["id"]}:context', body={'query': '未来发布', 'as_of': before})
            detail_before = request(client, 'POST', f'/api/local/memory/banks/{bank["id"]}:recall-details', body={'evidence_ids': [fact_id], 'as_of': before})
            m1_after = request(client, 'POST', f'/api/local/memory/banks/{bank["id"]}:recall', body={'query': '未来发布', 'as_of': after})
            m2_after = request(client, 'POST', f'/api/local/memory/banks/{bank["id"]}:context', body={'query': '未来发布', 'as_of': after})
            detail_after = request(client, 'POST', f'/api/local/memory/banks/{bank["id"]}:recall-details', body={'evidence_ids': [fact_id], 'as_of': after})
            values = {
                'm1_future_source_hidden': 1.0 if m1_before['memory_status'] == 'empty' else 0.0,
                'm2_context_future_source_hidden': 1.0 if m2_before['context_status'] == 'empty' else 0.0,
                'm2_detail_future_source_hidden': 1.0 if detail_before['unavailable_evidence_ids'] == [fact_id] else 0.0,
                'source_visible_at_as_of': 1.0 if (m1_after['evidence'][0]['evidence_id'] == fact_id and
                                                   m2_after['detail_catalog'][0]['evidence_id'] == fact_id and
                                                   detail_after['details'][0]['evidence_id'] == fact_id) else 0.0,
                'raw_source_export': 0.0 if '合成未来来源正文' not in json.dumps([m1_after, m2_after, detail_after], ensure_ascii=False) else 1.0,
            }
            expected = {
                'm1_future_source_hidden': 1.0, 'm2_context_future_source_hidden': 1.0,
                'm2_detail_future_source_hidden': 1.0, 'source_visible_at_as_of': 1.0, 'raw_source_export': 0.0,
            }
            return {
                'evaluation_version': CASESET_VERSION,
                'scope': 'synthetic as-of Source/Fact visibility across M1 Recall and M2-A Context/Detail',
                'model_calls': 0, 'external_calls': 0, 'results': values,
                'passed': all(values[name] == value for name, value in expected.items()),
                'not_evidence': [
                    'This is not semantic/vector retrieval, RRF/rerank, automatic summary, Entity Resolution, GraphQA, Reflect or final-answer quality.',
                    'The evaluation uses only synthetic source/fact content in a temporary SQLite database.',
                ],
            }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    result = run()
    encoded = json.dumps(result, ensure_ascii=False, indent=2) + '\n'
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(encoded)
    else:
        print(encoded, end='')
    if not result['passed']:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
