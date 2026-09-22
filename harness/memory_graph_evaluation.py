"""Synthetic deterministic M3-A evaluation; no model, source export, or network."""
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


CASESET_VERSION = 'memory-graph-m3a-synthetic@1'


def request(client, method, path, *, body=None, key=None):
    response = client.request(method, path, json=body, headers={'Idempotency-Key': key} if key else {})
    if response.status_code not in {200, 201}:
        raise RuntimeError(f'{method} {path} -> {response.status_code}: {response.text}')
    return response.json()


def source_and_facts(client, bank_id, ref, content, facts, key):
    return request(client, 'POST', f'/api/local/memory/banks/{bank_id}/retain', key=key, body={
        'source': {'source_ref': ref, 'content': content, 'occurred_at': '2026-09-20T09:00:00Z',
                   'data_classification': 'Internal'},
        'facts': [{
            'statement': statement, 'kind': 'fact', 'confidence': 0.9,
            'occurred_at': '2026-09-20T09:00:00Z', 'valid_from': '2026-09-20T09:00:00Z',
            'valid_to': None, 'supersedes_fact_id': None,
        } for statement in facts],
    })


def entity(client, bank_id, name, kind, support_fact_id, key):
    return request(client, 'POST', f'/api/local/memory/banks/{bank_id}/entities', key=key, body={
        'canonical_name': name, 'entity_type': kind, 'aliases': [], 'support_fact_id': support_fact_id,
        'valid_from': None, 'valid_to': None,
    })['entity']


def relation(client, bank_id, subject, predicate, object_, support_fact_id, key):
    return request(client, 'POST', f'/api/local/memory/banks/{bank_id}/relations', key=key, body={
        'subject_entity_id': subject, 'predicate': predicate, 'object_entity_id': object_,
        'support_fact_id': support_fact_id, 'confidence': 0.9, 'occurred_at': '2026-09-20T09:00:00Z',
        'valid_from': '2026-09-20T09:00:00Z', 'valid_to': None,
    })['relation']


def graph(client, bank_id, start, **extra):
    return request(client, 'POST', f'/api/local/memory/banks/{bank_id}:graph-recall', body={
        'start_entity_id': start, **extra,
    })


def run():
    with tempfile.TemporaryDirectory(prefix='harness-memory-graph-eval-') as directory:
        database = Path(directory) / 'evaluation.db'
        with TestClient(create_app(database, False), base_url='http://127.0.0.1') as client:
            main = request(client, 'POST', '/api/local/memory/banks', key='graph-eval-main', body={
                'name': 'graph-evaluation-main', 'scope': 'project', 'data_classification': 'Internal', 'retention_days': 90,
            })
            other = request(client, 'POST', '/api/local/memory/banks', key='graph-eval-other', body={
                'name': 'graph-evaluation-other', 'scope': 'project', 'data_classification': 'Internal', 'retention_days': 90,
            })
            retained = source_and_facts(client, main['id'], 'eval:graph', '合成 Graph 来源正文；不应输出。', [
                '小李负责支付系统。', '支付系统依赖风控服务。', '风控服务发生故障。',
            ], 'graph-eval-retain')
            person = entity(client, main['id'], '小李', 'person', retained['facts'][0]['id'], 'graph-eval-person')
            payment = entity(client, main['id'], '支付系统', 'system', retained['facts'][0]['id'], 'graph-eval-payment')
            risk = entity(client, main['id'], '风控服务', 'system', retained['facts'][1]['id'], 'graph-eval-risk')
            first = relation(client, main['id'], person['id'], 'responsible_for', payment['id'], retained['facts'][0]['id'], 'graph-eval-first')
            second = relation(client, main['id'], payment['id'], 'depends_on', risk['id'], retained['facts'][1]['id'], 'graph-eval-second')
            before = graph(client, main['id'], person['id'], max_hops=2, limit=10)
            cross = graph(client, other['id'], person['id'], max_hops=2)
            expired = graph(client, main['id'], person['id'], max_hops=2, as_of='2037-01-01T00:00:00Z')
            before_occurrence = graph(client, main['id'], person['id'], max_hops=2, as_of='2026-09-19T23:59:59Z')
            retracted = request(client, 'POST', f'/api/local/memory/sources/{retained["source"]["id"]}:retract', key='graph-eval-retract', body={})
            after_retract = graph(client, main['id'], person['id'], max_hops=2)

            deletion = request(client, 'POST', '/api/local/memory/banks', key='graph-eval-delete-bank', body={
                'name': 'graph-evaluation-delete', 'scope': 'project', 'data_classification': 'Internal', 'retention_days': 90,
            })
            deleted_input = source_and_facts(client, deletion['id'], 'eval:delete', '另一段合成来源正文。', [
                '甲负责乙系统。', '乙系统依赖丙服务。',
            ], 'graph-eval-delete-retain')
            a = entity(client, deletion['id'], '甲', 'person', deleted_input['facts'][0]['id'], 'graph-eval-delete-a')
            b = entity(client, deletion['id'], '乙系统', 'system', deleted_input['facts'][0]['id'], 'graph-eval-delete-b')
            c = entity(client, deletion['id'], '丙服务', 'system', deleted_input['facts'][1]['id'], 'graph-eval-delete-c')
            relation(client, deletion['id'], a['id'], 'responsible_for', b['id'], deleted_input['facts'][0]['id'], 'graph-eval-delete-one')
            relation(client, deletion['id'], b['id'], 'depends_on', c['id'], deleted_input['facts'][1]['id'], 'graph-eval-delete-two')
            deleted = request(client, 'DELETE', f'/api/local/memory/sources/{deleted_input["source"]["id"]}', key='graph-eval-delete')
            after_delete = graph(client, deletion['id'], a['id'], max_hops=2)

            two_hop = next((path for path in before['paths'] if path['hop_count'] == 2), None)
            values = {
                'two_hop_evidence_success': 1.0 if two_hop and [node['canonical_name'] for node in two_hop['nodes']] == ['小李', '支付系统', '风控服务'] else 0.0,
                'edge_provenance_coverage': 1.0 if two_hop and all(edge['support_evidence']['evidence_id'] and edge['support_evidence']['source_id'] for edge in two_hop['edges']) else 0.0,
                'temporal_filter_safety': 1.0 if (expired['memory_status'] == 'empty' and before_occurrence['memory_status'] == 'empty') else 0.0,
                'cross_bank_leakage': 0.0 if cross['paths'] == [] else 1.0,
                'retract_propagation': 1.0 if (retracted['retracted_entity_count'] == 3 and retracted['retracted_relation_count'] == 2
                                               and after_retract['memory_status'] == 'empty') else 0.0,
                'delete_completeness': 1.0 if (deleted['deleted_entity_count'] == 3 and deleted['deleted_relation_count'] == 2
                                                and after_delete['memory_status'] == 'empty') else 0.0,
                'raw_source_export': 0.0 if '合成 Graph 来源正文' not in json.dumps(before, ensure_ascii=False) else 1.0,
            }
            expected = {
                'two_hop_evidence_success': 1.0, 'edge_provenance_coverage': 1.0, 'temporal_filter_safety': 1.0,
                'cross_bank_leakage': 0.0, 'retract_propagation': 1.0, 'delete_completeness': 1.0,
                'raw_source_export': 0.0,
            }
            return {
                'evaluation_version': CASESET_VERSION,
                'scope': 'synthetic explicit entity/relation two-hop and lifecycle safety',
                'model_calls': 0, 'external_calls': 0, 'results': values,
                'passed': all(values[name] == value for name, value in expected.items()),
                'not_evidence': [
                    'This is not automatic entity extraction/resolution, natural-language GraphQA, semantic/vector retrieval, ranking, Reflect or final-answer quality.',
                    'The evaluation uses only synthetic source/fact/entity/relation content in a temporary SQLite database.',
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
