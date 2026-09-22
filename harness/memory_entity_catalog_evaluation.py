"""Synthetic deterministic M3-B entity-catalog evaluation; no model, source export, or network."""
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


CASESET_VERSION = 'memory-entity-catalog-m3b-synthetic@1'


def request(client, method, path, *, body=None, key=None, expected=(200, 201)):
    response = client.request(method, path, json=body, headers={'Idempotency-Key': key} if key else {})
    if response.status_code not in expected:
        raise RuntimeError(f'{method} {path} -> {response.status_code}: {response.text}')
    return response.json()


def retain(client, bank_id, ref, facts, key):
    return request(client, 'POST', f'/api/local/memory/banks/{bank_id}/retain', key=key, body={
        'source': {'source_ref': ref, 'content': '合成目录来源正文；不应输出。',
                   'occurred_at': '2026-09-20T09:00:00Z', 'data_classification': 'Internal'},
        'facts': [{
            'statement': statement, 'kind': 'fact', 'confidence': 0.9,
            'occurred_at': '2026-09-20T09:00:00Z', 'valid_from': '2026-09-20T09:00:00Z',
            'valid_to': None, 'supersedes_fact_id': None,
        } for statement in facts],
    })


def entity(client, bank_id, canonical_name, entity_type, support_fact_id, aliases, key):
    return request(client, 'POST', f'/api/local/memory/banks/{bank_id}/entities', key=key, body={
        'canonical_name': canonical_name, 'entity_type': entity_type, 'aliases': aliases,
        'support_fact_id': support_fact_id, 'valid_from': None, 'valid_to': None,
    })['entity']


def resolve(client, bank_id, name, **extra):
    return request(client, 'POST', f'/api/local/memory/banks/{bank_id}:resolve-entity', body={'name': name, **extra})


def run():
    with tempfile.TemporaryDirectory(prefix='harness-memory-entity-catalog-eval-') as directory:
        with TestClient(create_app(Path(directory) / 'evaluation.db', False), base_url='http://127.0.0.1') as client:
            main = request(client, 'POST', '/api/local/memory/banks', key='catalog-eval-main', body={
                'name': 'catalog-evaluation-main', 'scope': 'project', 'data_classification': 'Internal', 'retention_days': 90,
            })
            other = request(client, 'POST', '/api/local/memory/banks', key='catalog-eval-other', body={
                'name': 'catalog-evaluation-other', 'scope': 'project', 'data_classification': 'Internal', 'retention_days': 90,
            })
            retained = retain(client, main['id'], 'eval:catalog', [
                '支付系统由团队维护。', '支付项目正在推进。',
            ], 'catalog-eval-retain')
            system = entity(client, main['id'], '支付系统', 'system', retained['facts'][0]['id'], ['支付'], 'catalog-eval-system')
            project = entity(client, main['id'], '支付项目', 'project', retained['facts'][1]['id'], ['支付'], 'catalog-eval-project')
            canonical = resolve(client, main['id'], '支付系统')
            alias = resolve(client, main['id'], '支付', entity_type='system')
            ambiguous = resolve(client, main['id'], '支付')
            cross_bank = resolve(client, other['id'], '支付系统')
            before_occurrence = resolve(client, main['id'], '支付系统', as_of='2026-09-19T23:59:59Z')
            retracted = request(client, 'POST', f'/api/local/memory/sources/{retained["source"]["id"]}:retract',
                                 key='catalog-eval-retract', body={})
            after_retract = resolve(client, main['id'], '支付系统')
            values = {
                'canonical_exact_resolution': 1.0 if canonical['status'] == 'resolved' and canonical['candidates'][0]['entity_id'] == system['id'] else 0.0,
                'alias_exact_resolution': 1.0 if alias['status'] == 'resolved' and alias['candidates'][0]['entity_id'] == system['id'] else 0.0,
                'ambiguity_preserved': 1.0 if ambiguous['status'] == 'ambiguous' and {item['entity_id'] for item in ambiguous['candidates']} == {system['id'], project['id']} else 0.0,
                'type_filter_resolution': 1.0 if alias['candidates'][0]['entity_type'] == 'system' else 0.0,
                'cross_bank_leakage': 0.0 if cross_bank['candidates'] == [] else 1.0,
                'lifecycle_temporal_filter': 1.0 if before_occurrence['status'] == 'not_found' and retracted['retracted_entity_count'] == 2 and after_retract['status'] == 'not_found' else 0.0,
                'raw_source_export': 0.0 if '合成目录来源正文' not in json.dumps(canonical, ensure_ascii=False) else 1.0,
            }
            expected = {
                'canonical_exact_resolution': 1.0, 'alias_exact_resolution': 1.0, 'ambiguity_preserved': 1.0,
                'type_filter_resolution': 1.0, 'cross_bank_leakage': 0.0, 'lifecycle_temporal_filter': 1.0,
                'raw_source_export': 0.0,
            }
            return {
                'evaluation_version': CASESET_VERSION,
                'scope': 'synthetic exact canonical/alias catalog, ambiguity, temporal/lifecycle and Bank isolation',
                'model_calls': 0, 'external_calls': 0, 'results': values,
                'passed': all(values[name] == value for name, value in expected.items()),
                'not_evidence': [
                    'This is not semantic/vector matching, automatic Entity Resolution, entity merging, GraphQA, ranking, Reflect or final-answer quality.',
                    'The evaluation uses only synthetic source/fact/entity content in a temporary SQLite database.',
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
