"""Synthetic, deterministic M2-A evaluation; no model, source export, or network."""
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


CASESET_VERSION = 'memory-context-m2a-synthetic@1'


def request(client, method, path, *, body=None, key=None):
    headers = {'Idempotency-Key': key} if key else {}
    response = client.request(method, path, json=body, headers=headers)
    if response.status_code not in {200, 201}:
        raise RuntimeError(f'{method} {path} -> {response.status_code}: {response.text}')
    return response.json()


def fact(statement, kind, detail, *, supersedes=None, occurred='2026-09-20T10:00:00Z'):
    return {
        'statement': statement, 'kind': kind, 'detail': detail, 'confidence': 0.9,
        'occurred_at': occurred, 'valid_from': occurred, 'valid_to': None, 'supersedes_fact_id': supersedes,
    }


def retain(client, bank_id, source_ref, source_content, facts, key):
    return request(client, 'POST', f'/api/local/memory/banks/{bank_id}/retain', key=key, body={
        'source': {'source_ref': source_ref, 'content': source_content, 'occurred_at': '2026-09-20T10:00:00Z',
                   'data_classification': 'Internal'},
        'facts': facts,
    })


def run():
    with tempfile.TemporaryDirectory(prefix='harness-memory-context-eval-') as directory:
        database = Path(directory) / 'evaluation.db'
        with TestClient(create_app(database, False), base_url='http://127.0.0.1') as client:
            bank = request(client, 'POST', '/api/local/memory/banks', key='eval-main-bank', body={
                'name': 'memory-context-evaluation', 'scope': 'project', 'data_classification': 'Internal', 'retention_days': 90,
            })
            other = request(client, 'POST', '/api/local/memory/banks', key='eval-other-bank', body={
                'name': 'memory-context-other', 'scope': 'project', 'data_classification': 'Internal', 'retention_days': 90,
            })
            retained = retain(client, bank['id'], 'eval:current', '合成来源正文；不应输出。', [
                fact('本周完成客户演示。', 'objective', '本周五前交付演示版本，并保留回滚路径。'),
                fact('验收前禁止联网。', 'constraint', '只执行本机 SQLite 和离线检查。'),
                fact('方案 B 是当前决策。', 'decision', '方案 A 部署复杂，方案 B 优先满足本周上线。'),
                fact('当前处于评审状态。', 'state', '等待回归、双环境部署和 Evidence。'),
                fact('张三当前偏好下午开会。', 'preference', '最近两次会议都改在下午；上午常被临时会议占用。'),
            ], 'eval-current')
            old = retain(client, bank['id'], 'eval:old', '旧合成来源正文。', [
                fact('张三此前偏好上午开会。', 'preference', '三个月前的旧偏好。', occurred='2026-06-01T10:00:00Z'),
            ], 'eval-old')
            replacement = retain(client, bank['id'], 'eval:replacement', '新合成来源正文。', [
                fact('张三当前偏好下午开会。', 'preference', '近期的明确偏好，应覆盖旧事实。',
                     supersedes=old['facts'][0]['id']),
            ], 'eval-replacement')
            other_fact = retain(client, other['id'], 'eval:other', '另一 bank 的合成来源。', [
                fact('另一项目只在上午开会。', 'preference', '不能跨 bank 返回。'),
            ], 'eval-other')

            context = request(client, 'POST', f'/api/local/memory/banks/{bank["id"]}:context', body={
                'query': '本周演示', 'recent_turns': [{'role': 'user', 'content': '本轮只问本周演示计划。'}],
                'summary_limit': 8, 'catalog_limit': 12,
            })
            summary_items = [item for section in context['summary']['sections'] for item in section['items']]
            catalog_ids = {item['evidence_id'] for item in context['detail_catalog']}
            expected = retained['facts'][0]
            detail = request(client, 'POST', f'/api/local/memory/banks/{bank["id"]}:recall-details', body={
                'evidence_ids': [expected['id']],
            })
            preference_context = request(client, 'POST', f'/api/local/memory/banks/{bank["id"]}:context', body={
                'query': '张三开会', 'summary_limit': 8, 'catalog_limit': 12,
            })
            preference_ids = {item['evidence_id'] for item in preference_context['detail_catalog']}
            stale_detail = request(client, 'POST', f'/api/local/memory/banks/{bank["id"]}:recall-details', body={
                'evidence_ids': [old['facts'][0]['id']],
            })
            cross_detail = request(client, 'POST', f'/api/local/memory/banks/{bank["id"]}:recall-details', body={
                'evidence_ids': [other_fact['facts'][0]['id']],
            })

            values = {
                'critical_fact_recall_at_12': 1.0 if expected['id'] in catalog_ids else 0.0,
                'summary_fidelity': 1.0 if any(item['evidence_id'] == expected['id'] and item['kind'] == 'objective'
                                                for item in summary_items) else 0.0,
                'detail_exactness': 1.0 if detail['details'] and detail['details'][0]['detail'].startswith('本周五前') else 0.0,
                'supersede_safety': 1.0 if (replacement['facts'][0]['id'] in preference_ids and old['facts'][0]['id'] not in preference_ids
                                             and stale_detail['memory_status'] == 'empty') else 0.0,
                'cross_bank_leakage': 0.0 if not cross_detail['details'] else 1.0,
                'recent_turn_persistence': 0.0 if context['safety']['recent_turns_persisted'] is False else 1.0,
                'raw_source_export': 0.0 if '合成来源正文' not in json.dumps({'context': context, 'detail': detail}, ensure_ascii=False) else 1.0,
            }
            expected_values = {
                'critical_fact_recall_at_12': 1.0, 'summary_fidelity': 1.0, 'detail_exactness': 1.0,
                'supersede_safety': 1.0, 'cross_bank_leakage': 0.0, 'recent_turn_persistence': 0.0,
                'raw_source_export': 0.0,
            }
            passed = all(values[name] == expected_value for name, expected_value in expected_values.items())
            return {
                'evaluation_version': CASESET_VERSION,
                'scope': 'synthetic deterministic Fact Capsule, FTS5 catalog, exact detail and lifecycle safety',
                'model_calls': 0,
                'external_calls': 0,
                'results': values,
                'passed': passed,
                'not_evidence': [
                    'This is not semantic/vector retrieval, RRF/rerank, model-summary, final-answer quality, or production data evaluation.',
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
