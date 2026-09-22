"""Source-first M1 Memory Plane. It stores explicit evidence, not chat transcripts."""
from __future__ import annotations

import json
import re
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

from jsonschema import Draft202012Validator, FormatChecker

from .analysis import Problem, digest
from .store import dumps, now, uid


ROOT = Path(__file__).resolve().parents[1]
CONTRACT = json.loads((ROOT / 'specs/v1/memory-plane.schema.json').read_text())
CONTEXT_CONTRACT = json.loads((ROOT / 'specs/v1/memory-context.schema.json').read_text())
GRAPH_CONTRACT = json.loads((ROOT / 'specs/v1/memory-graph.schema.json').read_text())
ENTITY_CATALOG_CONTRACT = json.loads((ROOT / 'specs/v1/memory-entity-catalog.schema.json').read_text())
LINEAGE_CONTRACT = json.loads((ROOT / 'specs/v1/memory-fact-lineage.schema.json').read_text())
SEMANTIC_ADMISSION_CONTRACT = json.loads((ROOT / 'specs/v1/memory-semantic-admission.schema.json').read_text())
SEMANTIC_ADMISSION_STATE = ROOT / 'harness/semantic-retrieval-admission.json'
SENSITIVE_INPUT = re.compile(r'(?:\b(?:api[_ -]?key|client[_ -]?secret|access[_ -]?token|refresh[_ -]?token|password)\s*[:=]|\bsk-[A-Za-z0-9_-]{10,}|\bAKIA[0-9A-Z]{16}\b)', re.I)
WORD = re.compile(r'[a-z0-9_]{2,}|[\u4e00-\u9fff]+', re.I)


def validate_contract(name, value):
    schema = {'$ref': '#/$defs/' + name, '$defs': CONTRACT['$defs']}
    if list(Draft202012Validator(schema, format_checker=FormatChecker()).iter_errors(value)):
        raise Problem('VALIDATION_ERROR', '请求不符合 Memory Plane M1 契约。', 422)


def validate_context_contract(name, value):
    schema = {'$ref': '#/$defs/' + name, '$defs': CONTEXT_CONTRACT['$defs']}
    if list(Draft202012Validator(schema, format_checker=FormatChecker()).iter_errors(value)):
        raise Problem('VALIDATION_ERROR', '请求不符合 Memory Context M2-A 契约。', 422)


def validate_graph_contract(name, value):
    schema = {'$ref': '#/$defs/' + name, '$defs': GRAPH_CONTRACT['$defs']}
    if list(Draft202012Validator(schema, format_checker=FormatChecker()).iter_errors(value)):
        raise Problem('VALIDATION_ERROR', '请求不符合 Memory Graph M3-A 契约。', 422)


def validate_entity_catalog_contract(name, value):
    schema = {'$ref': '#/$defs/' + name, '$defs': ENTITY_CATALOG_CONTRACT['$defs']}
    if list(Draft202012Validator(schema, format_checker=FormatChecker()).iter_errors(value)):
        raise Problem('VALIDATION_ERROR', '请求不符合 Memory Entity Catalog M3-B 契约。', 422)


def validate_lineage_contract(name, value):
    schema = {'$ref': '#/$defs/' + name, '$defs': LINEAGE_CONTRACT['$defs']}
    if list(Draft202012Validator(schema, format_checker=FormatChecker()).iter_errors(value)):
        raise Problem('VALIDATION_ERROR', '请求不符合 Fact Lineage 契约。', 422)


def semantic_admission_status(path=SEMANTIC_ADMISSION_STATE):
    """Fail closed: an invalid Gate can never enable semantic retrieval."""
    try:
        value = json.loads(Path(path).read_text())
        errors = list(Draft202012Validator(SEMANTIC_ADMISSION_CONTRACT).iter_errors(value))
    except (OSError, json.JSONDecodeError) as exc:
        return {'status': 'invalid_not_admitted', 'admission_enabled': False, 'runtime_enabled': False,
                'model_calls': 0, 'external_calls': 0, 'blocker_count': 1, 'error': type(exc).__name__}
    if errors:
        return {'status': 'invalid_not_admitted', 'admission_enabled': False, 'runtime_enabled': False,
                'model_calls': 0, 'external_calls': 0, 'blocker_count': 1, 'error': 'schema_validation'}
    return {
        'status': value['status'], 'admission_enabled': value['enabled'], 'runtime_enabled': False,
        'model_calls': value['model_calls'], 'external_calls': value['external_calls'],
        'blocker_count': len(value['blockers']), 'error': None,
    }


def canonical_time(value, field):
    if not isinstance(value, str):
        raise Problem('VALIDATION_ERROR', field + ' 必须是带时区的 RFC 3339 时间。', 422)
    try:
        parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
    except ValueError:
        raise Problem('VALIDATION_ERROR', field + ' 必须是带时区的 RFC 3339 时间。', 422) from None
    if parsed.tzinfo is None:
        raise Problem('VALIDATION_ERROR', field + ' 必须包含时区。', 422)
    return parsed.astimezone(timezone.utc).isoformat().replace('+00:00', 'Z')


def parse_canonical(value):
    return datetime.fromisoformat(value.replace('Z', '+00:00'))


def _query_terms(query):
    lowered = query.casefold()
    terms = set(WORD.findall(lowered))
    for chunk in re.findall(r'[\u4e00-\u9fff]+', lowered):
        terms.update(chunk)
    return sorted(terms, key=lambda item: (-len(item), item))


def _fts_terms(value):
    """Bounded CJK/Latin terms for a local FTS5 projection, never semantic embeddings."""
    text = value.casefold()
    terms = set(re.findall(r'[a-z0-9_]{2,}', text))
    for chunk in re.findall(r'[\u4e00-\u9fff]+', text):
        terms.add(chunk)
        if len(chunk) == 1:
            terms.add(chunk)
            continue
        for width in (2, 3):
            terms.update(chunk[index:index + width] for index in range(0, len(chunk) - width + 1))
    return sorted(terms, key=lambda item: (-len(item), item))[:512]


def _fts_match_query(query):
    terms = _fts_terms(query)
    if not terms:
        return None
    return ' OR '.join('"' + term.replace('"', '""') + '"' for term in terms[:32])


class MemoryPlane:
    """Local-admin M1/M2-A/M3-A/M3-B evidence lifecycle; no models, vectors, or Product events."""

    def __init__(self, store):
        self.store = store
        self._fts_ready = False
        self._fts_error = None
        self._ensure_keyword_index()

    def _ensure_keyword_index(self):
        """Create/rebuild an expendable FTS projection without making M1 unavailable on SQLite builds lacking FTS5."""
        try:
            with self.store.transaction() as db:
                db.execute("CREATE VIRTUAL TABLE IF NOT EXISTS memory_fact_fts USING fts5(fact_id UNINDEXED, bank_id UNINDEXED, terms, tokenize='unicode61 remove_diacritics 2')")
                self._rebuild_keyword_index(db)
            self._fts_ready, self._fts_error = True, None
        except sqlite3.OperationalError as exc:
            self._fts_ready, self._fts_error = False, str(exc)

    @staticmethod
    def _index_fact(db, fact):
        terms = ' '.join(_fts_terms(fact['statement']))
        db.execute('INSERT INTO memory_fact_fts(fact_id,bank_id,terms) VALUES(?,?,?)',
                   (fact['id'], fact['bank_id'], terms))

    def _rebuild_keyword_index(self, db):
        db.execute('DELETE FROM memory_fact_fts')
        sources = {row['id']: row for row in (json.loads(item['doc']) for item in db.execute('SELECT doc FROM memory_sources'))
                   if row['status'] == 'active'}
        for fact in (json.loads(item['doc']) for item in db.execute('SELECT doc FROM memory_facts')):
            if fact['status'] == 'active' and fact['source_id'] in sources:
                self._index_fact(db, fact)

    def _remove_index_entries(self, db, fact_ids):
        if self._fts_ready or self._fts_error is None:
            db.executemany('DELETE FROM memory_fact_fts WHERE fact_id=?', ((fact_id,) for fact_id in fact_ids))

    def _fts_candidate_ids(self, bank_id, query):
        if not self._fts_ready:
            return None
        expression = _fts_match_query(query)
        if not expression:
            return set()
        try:
            with self.store.lock:
                rows = self.store.db.execute(
                    'SELECT fact_id FROM memory_fact_fts WHERE memory_fact_fts MATCH ? AND bank_id=? LIMIT 80',
                    (expression, bank_id),
                ).fetchall()
            return {row['fact_id'] for row in rows}
        except sqlite3.OperationalError:
            return None

    @staticmethod
    def _idempotency_key(key):
        if not isinstance(key, str) or not 1 <= len(key) <= 128:
            raise Problem('VALIDATION_ERROR', '必须提供 1–128 字符的 Idempotency-Key。', 422)

    def _idempotent(self, scope, key, body, action):
        self._idempotency_key(key)
        request_digest = digest(dumps(body).encode())
        with self.store.transaction() as db:
            previous = db.execute('SELECT digest,response FROM idempotency WHERE scope=? AND key=?', (scope, key)).fetchone()
            if previous:
                if previous['digest'] != request_digest:
                    raise Problem('CONFLICT', '同一幂等键已用于不同请求。', 409)
                return json.loads(previous['response'])
            response = action(db)
            db.execute('INSERT INTO idempotency VALUES(?,?,?,?)', (scope, key, request_digest, dumps(response)))
            return response

    @staticmethod
    def _audit(db, bank_id, kind, target_id, metadata):
        record = {
            'id': uid('memaudit'), 'bank_id': bank_id, 'event_type': kind, 'target_id': target_id,
            'occurred_at': now(), 'metadata': metadata,
        }
        db.execute('INSERT INTO memory_audit VALUES(?,?,?)', (record['id'], bank_id, dumps(record)))
        return record

    @staticmethod
    def _bank(db, bank_id):
        row = db.execute('SELECT doc FROM memory_banks WHERE id=?', (bank_id,)).fetchone()
        if not row:
            raise Problem('MEMORY_BANK_NOT_FOUND', 'Memory Bank 不存在。', 404)
        return json.loads(row['doc'])

    @staticmethod
    def _source(db, source_id):
        row = db.execute('SELECT doc FROM memory_sources WHERE id=?', (source_id,)).fetchone()
        if not row:
            raise Problem('MEMORY_SOURCE_NOT_FOUND', 'Memory Source 不存在。', 404)
        return json.loads(row['doc'])

    def runtime_status(self):
        semantic_gate = semantic_admission_status()
        return {
            'mode': 'memory-plane-m3b@1', 'status': 'available_local_admin',
            'write_mode': 'explicit_source_fact_entity_relation_only',
            'recall_mode': ['keyword', 'temporal', 'context_catalog', 'detail_by_id', 'explicit_graph_temporal'],
            'model_extraction': False, 'reflect': False, 'vector_index': False, 'graph_index': False,
            'graph_recall': {'engine': 'sqlite-explicit-relation-store@1', 'max_hops': 2,
                             'automatic_entity_resolution': False},
            'entity_catalog': {'match_mode': 'exact_canonical_or_alias_casefold', 'automatic_entity_resolution': False,
                               'max_candidates': 16},
            'product_task_run_integration': False,
            'keyword_index': {'engine': 'sqlite-fts5@1' if self._fts_ready else None, 'ready': self._fts_ready,
                              'rebuildable_from': 'canonical_active_facts', 'error': self._fts_error},
            'as_of_visibility': {'source_occurred_at': True, 'fact_occurred_at': True, 'fact_validity_window': True},
            'semantic_retrieval': semantic_gate,
            'summary_mode': 'fact_derived_not_model_generated',
            'recent_turns': 'caller_provided_transient_not_persisted',
            'note': 'M3-A 只允许显式、可追溯 Fact 支撑的 Entity/Relation 两跳回读；M3-B 只提供精确名称目录。没有语义向量、自动实体抽取/消歧或模型调用。',
        }

    def banks(self):
        return {'items': self.store.memory_banks(), 'runtime': self.runtime_status()}

    def create_bank(self, body, key):
        validate_contract('bank_create_request', body)
        name = body['name'].strip()
        if not name or SENSITIVE_INPUT.search(name):
            raise Problem('VALIDATION_ERROR', 'Memory Bank 名称无效或包含敏感内容。', 422)
        normalized = {**body, 'name': name}

        def create(db):
            rows = db.execute('SELECT doc FROM memory_banks').fetchall()
            if any(json.loads(row['doc'])['name'].casefold() == name.casefold() for row in rows):
                raise Problem('CONFLICT', 'Memory Bank 名称已存在。', 409)
            bank = {
                'id': uid('membank'), 'workspace_id': 'ws_local', 'owner': 'local_admin', **normalized,
                'policy_version': 'memory-policy@1', 'created_at': now(),
            }
            validate_contract('memory_bank', bank)
            db.execute('INSERT INTO memory_banks VALUES(?,?)', (bank['id'], dumps(bank)))
            self._audit(db, bank['id'], 'memory.bank.created', bank['id'], {'name_sha256': digest(name.encode())})
            return bank

        return self._idempotent('memory:banks', key, normalized, create)

    def bank_detail(self, bank_id):
        bank = self.store.memory_bank(bank_id)
        with self.store.lock:
            source_count = self.store.db.execute('SELECT count(*) FROM memory_sources WHERE bank_id=?', (bank_id,)).fetchone()[0]
            fact_count = self.store.db.execute('SELECT count(*) FROM memory_facts WHERE bank_id=?', (bank_id,)).fetchone()[0]
        return {'bank': bank, 'counts': {'sources': source_count, 'facts': fact_count}, 'runtime': self.runtime_status()}

    def retain(self, bank_id, body, key):
        validate_contract('retain_request', body)
        source_input = body['source']
        if source_input['data_classification'] == 'Restricted' or SENSITIVE_INPUT.search(source_input['content']):
            raise Problem('MEMORY_RETAIN_REJECTED', '来源含 Restricted 或凭证样式内容，不能写入长期记忆。', 422)
        source = {
            **source_input, 'source_ref': source_input['source_ref'].strip(),
            'content': source_input['content'].strip(),
            'occurred_at': canonical_time(source_input['occurred_at'], 'source.occurred_at'),
        }
        if not source['source_ref'] or not source['content']:
            raise Problem('VALIDATION_ERROR', '来源引用和内容不能为空。', 422)
        facts = []
        fact_seen = set()
        for value in body['facts']:
            statement = value['statement'].strip()
            detail = value.get('detail')
            if isinstance(detail, str):
                detail = detail.strip()
            if not statement or SENSITIVE_INPUT.search(statement) or (detail and SENSITIVE_INPUT.search(detail)):
                raise Problem('MEMORY_RETAIN_REJECTED', 'Fact 为空或包含凭证样式内容。', 422)
            if detail and (detail in source['content'] or source['content'] in detail):
                raise Problem('MEMORY_RETAIN_REJECTED', 'Fact detail 不能复制原始 Source 正文；请提交有界的派生细节。', 422)
            occurred_at = canonical_time(value['occurred_at'], 'fact.occurred_at')
            valid_from = canonical_time(value['valid_from'], 'fact.valid_from') if value.get('valid_from') else None
            valid_to = canonical_time(value['valid_to'], 'fact.valid_to') if value.get('valid_to') else None
            if valid_from and valid_to and parse_canonical(valid_to) < parse_canonical(valid_from):
                raise Problem('VALIDATION_ERROR', 'Fact valid_to 不能早于 valid_from。', 422)
            signature = (statement.casefold(), value['kind'], occurred_at)
            if signature in fact_seen:
                raise Problem('VALIDATION_ERROR', '同一 Retain 请求含重复 Fact。', 422)
            fact_seen.add(signature)
            facts.append({
                'statement': statement, 'kind': value['kind'], 'confidence': value['confidence'], 'occurred_at': occurred_at,
                'detail': detail or None, 'valid_from': valid_from, 'valid_to': valid_to,
                'supersedes_fact_id': value.get('supersedes_fact_id') or None,
            })
        normalized = {'source': source, 'facts': facts}

        def write(db):
            bank = self._bank(db, bank_id)
            if bank['data_classification'] == 'Public' and source['data_classification'] != 'Public':
                raise Problem('MEMORY_CLASSIFICATION_DENIED', 'Public Memory Bank 不能写入 Internal 来源。', 403)
            content_sha = digest(source['content'].encode())
            previous = db.execute('SELECT doc FROM memory_sources WHERE bank_id=? AND content_sha256=?',
                                  (bank_id, content_sha)).fetchone()
            if previous:
                existing = json.loads(previous['doc'])
                return {'source': _source_view(existing), 'facts': [], 'deduplicated': True,
                        'audit_id': None, 'note': '相同来源内容已存在；没有再次写入 Fact。'}
            recorded_at = now()
            expires_at = (parse_canonical(recorded_at) + timedelta(days=bank['retention_days'])).isoformat().replace('+00:00', 'Z')
            source_doc = {
                'id': uid('memsrc'), 'bank_id': bank_id, 'source_ref': source['source_ref'], 'content': source['content'],
                'content_sha256': content_sha, 'data_classification': source['data_classification'],
                'occurred_at': source['occurred_at'], 'recorded_at': recorded_at, 'expires_at': expires_at,
                'status': 'active', 'retracted_at': None,
            }
            db.execute('INSERT INTO memory_sources VALUES(?,?,?,?)',
                       (source_doc['id'], bank_id, content_sha, dumps(source_doc)))
            result_facts = []
            for input_fact in facts:
                superseded = None
                target_id = input_fact['supersedes_fact_id']
                if target_id:
                    target_row = db.execute('SELECT doc FROM memory_facts WHERE id=? AND bank_id=?', (target_id, bank_id)).fetchone()
                    if not target_row:
                        raise Problem('MEMORY_FACT_NOT_FOUND', '要纠正的 Fact 不在此 Memory Bank。', 404)
                    superseded = json.loads(target_row['doc'])
                    if superseded['status'] != 'active':
                        raise Problem('MEMORY_FACT_NOT_ACTIVE', '只能纠正 active Fact。', 409)
                fact = {
                    'id': uid('memfact'), 'bank_id': bank_id, 'source_id': source_doc['id'],
                    'statement': input_fact['statement'], 'kind': input_fact['kind'], 'confidence': input_fact['confidence'],
                    'detail': input_fact['detail'],
                    'occurred_at': input_fact['occurred_at'], 'valid_from': input_fact['valid_from'], 'valid_to': input_fact['valid_to'],
                    'status': 'active', 'supersedes_fact_id': target_id, 'superseded_by_fact_id': None, 'recorded_at': now(),
                }
                db.execute('INSERT INTO memory_facts VALUES(?,?,?,?)', (fact['id'], bank_id, source_doc['id'], dumps(fact)))
                if superseded:
                    superseded['status'] = 'superseded'
                    superseded['superseded_by_fact_id'] = fact['id']
                    db.execute('UPDATE memory_facts SET doc=? WHERE id=?', (dumps(superseded), superseded['id']))
                    self._remove_index_entries(db, [superseded['id']])
                    graph_invalidated = self._invalidate_graph_for_facts(
                        db, bank_id, [superseded['id']], 'superseded')
                    self._audit(db, bank_id, 'memory.fact.superseded', superseded['id'], {
                        'replacement_fact_id': fact['id'], 'source_id': source_doc['id'],
                        'invalidated_entity_count': graph_invalidated['entities'],
                        'invalidated_relation_count': graph_invalidated['relations'],
                    })
                self._index_fact(db, fact)
                result_facts.append(_fact_view(fact))
            audit = self._audit(db, bank_id, 'memory.source.retained', source_doc['id'], {
                'source_sha256': content_sha, 'fact_count': len(result_facts), 'data_classification': source_doc['data_classification'],
            })
            return {'source': _source_view(source_doc), 'facts': result_facts, 'deduplicated': False,
                    'audit_id': audit['id'], 'note': '来源和显式 Fact 已写入；未进行模型抽取或 Reflect。'}

        return self._idempotent('memory:retain:' + bank_id, key, normalized, write)

    def recall(self, bank_id, body):
        validate_contract('recall_request', body)
        bank = self.store.memory_bank(bank_id)
        query = body['query'].strip()
        if not query or SENSITIVE_INPUT.search(query):
            raise Problem('MEMORY_RECALL_REJECTED', '查询为空或包含凭证样式内容。', 422)
        as_of = canonical_time(body['as_of'], 'as_of') if body.get('as_of') else now()
        point = parse_canonical(as_of)
        terms = _query_terms(query)
        if not terms:
            raise Problem('MEMORY_RECALL_REJECTED', '查询不包含可用关键词。', 422)
        candidate_ids = self._fts_candidate_ids(bank_id, query)
        sources, facts = self._active_source_fact_documents(bank_id, point)
        evidence = []
        for fact in facts.values():
            if candidate_ids is not None and fact['id'] not in candidate_ids:
                continue
            source = sources.get(fact['source_id'])
            if not source:
                continue
            text = fact['statement'].casefold()
            matches = [term for term in terms if term in text]
            if not matches:
                continue
            exact = 20 if query.casefold() in text else 0
            score = exact + sum(min(5, text.count(term)) for term in matches)
            evidence.append({
                'evidence_id': fact['id'], 'type': 'fact', 'statement': fact['statement'], 'kind': fact['kind'],
                'confidence': fact['confidence'], 'occurred_at': fact['occurred_at'], 'recorded_at': fact['recorded_at'],
                'valid_from': fact['valid_from'], 'valid_to': fact['valid_to'], 'status': fact['status'],
                'source_evidence': {'source_id': source['id'], 'source_ref': source['source_ref'],
                                    'content_sha256': source['content_sha256'], 'occurred_at': source['occurred_at']},
                'score_explanation': {'channel': 'keyword', 'matched_terms': matches, 'keyword_score': score,
                                      'temporal_as_of': as_of},
            })
        evidence.sort(key=lambda item: (item['score_explanation']['keyword_score'], item['occurred_at'], item['evidence_id']), reverse=True)
        bundle = {
            'schema_version': 'evidence-bundle@1', 'bank_id': bank['id'], 'query': query,
            'memory_status': 'available' if evidence else 'empty', 'channels': ['keyword', 'temporal'],
            'evidence': evidence[:body.get('limit', 5)],
        }
        validate_contract('evidence_bundle', bundle)
        return bundle

    def fact_lineage(self, bank_id, body):
        validate_lineage_contract('request', body)
        bank = self.store.memory_bank(bank_id)
        as_of = canonical_time(body['as_of'], 'as_of') if body.get('as_of') else now()
        point = parse_canonical(as_of)
        sources, _ = self._active_source_fact_documents(bank['id'], point)
        with self.store.lock:
            rows = self.store.db.execute('SELECT doc FROM memory_facts WHERE bank_id=?', (bank['id'],)).fetchall()
        visible = {fact['id']: fact for row in rows if (fact := json.loads(row['doc']))['status'] in {'active', 'superseded'}
                   and fact['source_id'] in sources and self._within_window(fact, point)}
        start_id, max_depth = body['fact_id'], body.get('max_depth', 6)
        facts, current_id, seen = [], start_id, set()
        while current_id and current_id not in seen and len(facts) < max_depth:
            fact = visible.get(current_id)
            if not fact or fact['status'] not in {'active', 'superseded'}:
                break
            source = sources.get(fact['source_id'])
            if not source:
                break
            seen.add(current_id)
            facts.append({
                'evidence_id': fact['id'], 'statement': fact['statement'], 'kind': fact['kind'], 'status': fact['status'],
                'occurred_at': fact['occurred_at'], 'valid_from': fact['valid_from'], 'valid_to': fact['valid_to'],
                'supersedes_fact_id': fact['supersedes_fact_id'], 'superseded_by_fact_id': fact['superseded_by_fact_id'],
                'applicability': 'current_applicable' if fact['status'] == 'active' else 'historical',
                'source_evidence': {'source_id': source['id'], 'source_ref': source['source_ref'],
                                    'content_sha256': source['content_sha256'], 'occurred_at': source['occurred_at']},
            })
            current_id = fact['supersedes_fact_id']
        bundle = {
            'schema_version': 'fact-lineage-evidence@1', 'bank_id': bank['id'], 'fact_id': start_id, 'as_of': as_of,
            'lineage_status': 'available' if facts else 'empty', 'facts': facts,
            'truncated': bool(current_id and current_id not in seen),
            'safety': {'raw_source_content_included': False, 'automatic_conflict_resolution': False, 'model_calls': 0},
        }
        validate_lineage_contract('bundle', bundle)
        return bundle

    def _active_source_fact_documents(self, bank_id, point):
        """Canonical as-of visibility for all Source-backed Fact read paths."""
        with self.store.lock:
            source_rows = self.store.db.execute('SELECT doc FROM memory_sources WHERE bank_id=?', (bank_id,)).fetchall()
            fact_rows = self.store.db.execute('SELECT doc FROM memory_facts WHERE bank_id=?', (bank_id,)).fetchall()
        sources = {source['id']: source for row in source_rows if (source := json.loads(row['doc']))['status'] == 'active'
                   and parse_canonical(source['occurred_at']) <= point and parse_canonical(source['expires_at']) >= point}
        facts = {fact['id']: fact for row in fact_rows if (fact := json.loads(row['doc']))['status'] == 'active'
                 and fact['source_id'] in sources and self._within_window(fact, point)}
        return sources, facts

    def _context_candidates(self, bank_id, query, as_of):
        point = parse_canonical(as_of)
        candidate_ids = self._fts_candidate_ids(bank_id, query)
        if candidate_ids is None:
            raise Problem('MEMORY_INDEX_UNAVAILABLE', 'M2-A 关键词索引不可用；不能把索引故障伪装成无历史。', 503)
        terms = _query_terms(query)
        sources, facts = self._active_source_fact_documents(bank_id, point)
        results = []
        for fact in facts.values():
            source = sources.get(fact['source_id'])
            if not source or fact['id'] not in candidate_ids:
                continue
            text = fact['statement'].casefold()
            matched = [term for term in terms if term in text]
            score = (20 if query.casefold() in text else 0) + sum(min(5, text.count(term)) for term in matched)
            results.append((score, fact, source))
        return sorted(results, key=lambda item: (item[0], item[1]['occurred_at'], item[1]['id']), reverse=True)

    def context(self, bank_id, body):
        validate_context_contract('context_request', body)
        bank = self.store.memory_bank(bank_id)
        query = body['query'].strip()
        recent_turns = body.get('recent_turns') or []
        if not query or SENSITIVE_INPUT.search(query) or any(SENSITIVE_INPUT.search(turn['content']) for turn in recent_turns):
            raise Problem('MEMORY_CONTEXT_REJECTED', '查询或暂时上下文含无效或凭证样式内容。', 422)
        as_of = canonical_time(body['as_of'], 'as_of') if body.get('as_of') else now()
        candidates = self._context_candidates(bank['id'], query, as_of)
        summary_limit = body.get('summary_limit', 6)
        catalog_limit = body.get('catalog_limit', 10)
        selected = candidates[:max(summary_limit, catalog_limit)]
        sections = []
        for kind in ('objective', 'entity', 'fact', 'constraint', 'preference', 'decision', 'state'):
            items = [{
                'evidence_id': fact['id'], 'kind': fact['kind'], 'statement': fact['statement'],
                'occurred_at': fact['occurred_at'], 'source_id': source['id'],
            } for _, fact, source in selected[:summary_limit] if fact['kind'] == kind]
            sections.append({'kind': kind, 'items': items})
        catalog = [{
            'evidence_id': fact['id'], 'kind': fact['kind'], 'statement_preview': fact['statement'][:240],
            'occurred_at': fact['occurred_at'], 'source_id': source['id'], 'detail_available': bool(fact.get('detail')),
        } for _, fact, source in selected[:catalog_limit]]
        capsule = {
            'schema_version': 'memory-context-capsule@1', 'bank_id': bank['id'], 'query': query, 'as_of': as_of,
            'context_status': 'available' if selected else 'empty', 'recent_turns': recent_turns,
            'summary': {'format': 'fact-derived-summary@1', 'is_model_generated': False, 'sections': sections},
            'detail_catalog': catalog,
            'next_action': {'operation': 'memory.recall_details@1',
                            'eligible_evidence_ids': [item['evidence_id'] for item in catalog], 'max_items': 8},
            'safety': {'recent_turns_persisted': False, 'raw_source_content_included': False, 'model_calls': 0},
        }
        validate_context_contract('context_capsule', capsule)
        return capsule

    def recall_details(self, bank_id, body):
        validate_context_contract('detail_recall_request', body)
        bank = self.store.memory_bank(bank_id)
        as_of = canonical_time(body['as_of'], 'as_of') if body.get('as_of') else now()
        point = parse_canonical(as_of)
        requested = body['evidence_ids']
        sources, facts = self._active_source_fact_documents(bank['id'], point)
        details, unavailable = [], []
        for evidence_id in requested:
            fact = facts.get(evidence_id)
            source = sources.get(fact['source_id']) if fact else None
            if not fact or not source:
                unavailable.append(evidence_id)
                continue
            details.append({
                'evidence_id': fact['id'], 'kind': fact['kind'], 'statement': fact['statement'],
                'detail': fact.get('detail') or fact['statement'], 'occurred_at': fact['occurred_at'],
                'source_evidence': {'source_id': source['id'], 'source_ref': source['source_ref'],
                                    'content_sha256': source['content_sha256'], 'occurred_at': source['occurred_at']},
            })
        bundle = {
            'schema_version': 'memory-detail-bundle@1', 'bank_id': bank['id'], 'as_of': as_of,
            'memory_status': 'available' if details and not unavailable else ('partial' if details else 'empty'),
            'details': details, 'unavailable_evidence_ids': unavailable,
            'safety': {'raw_source_content_included': False, 'model_calls': 0},
        }
        validate_context_contract('detail_bundle', bundle)
        return bundle

    @staticmethod
    def _within_window(value, point):
        return not ((value.get('occurred_at') and parse_canonical(value['occurred_at']) > point) or
                    (value.get('valid_from') and parse_canonical(value['valid_from']) > point) or
                    (value.get('valid_to') and parse_canonical(value['valid_to']) < point))

    def _active_support_fact(self, db, bank_id, fact_id, point=None):
        """Return a source-backed active Fact in this Bank without exposing cross-Bank existence."""
        point = point or parse_canonical(now())
        row = db.execute('SELECT doc FROM memory_facts WHERE id=? AND bank_id=?', (fact_id, bank_id)).fetchone()
        if not row:
            raise Problem('MEMORY_GRAPH_SUPPORT_FACT_NOT_FOUND', 'Graph 支撑 Fact 不在此 Memory Bank。', 404)
        fact = json.loads(row['doc'])
        source_row = db.execute('SELECT doc FROM memory_sources WHERE id=? AND bank_id=?',
                                (fact['source_id'], bank_id)).fetchone()
        source = json.loads(source_row['doc']) if source_row else None
        if (fact['status'] != 'active' or not source or source['status'] != 'active' or
                parse_canonical(source['expires_at']) < point or not self._within_window(fact, point)):
            raise Problem('MEMORY_GRAPH_SUPPORT_FACT_NOT_ACTIVE', 'Graph 支撑 Fact 或其来源当前无效。', 409)
        return fact, source

    @staticmethod
    def _graph_entity_view(entity):
        return {key: entity[key] for key in ('id', 'bank_id', 'canonical_name', 'entity_type', 'aliases',
                                              'support_fact_id', 'valid_from', 'valid_to', 'status', 'recorded_at')}

    @staticmethod
    def _graph_relation_view(relation):
        return {key: relation[key] for key in ('id', 'bank_id', 'subject_entity_id', 'predicate', 'object_entity_id',
                                                'support_fact_id', 'confidence', 'occurred_at', 'valid_from',
                                                'valid_to', 'status', 'recorded_at')}

    @staticmethod
    def _normalize_entity_input(body):
        canonical_name = body['canonical_name'].strip()
        aliases = []
        seen = {canonical_name.casefold()}
        for alias in body['aliases']:
            cleaned = alias.strip()
            if cleaned and cleaned.casefold() not in seen:
                aliases.append(cleaned)
                seen.add(cleaned.casefold())
        if not canonical_name or SENSITIVE_INPUT.search(canonical_name) or any(SENSITIVE_INPUT.search(alias) for alias in aliases):
            raise Problem('MEMORY_GRAPH_REJECTED', 'Entity 名称无效或包含凭证样式内容。', 422)
        valid_from = canonical_time(body['valid_from'], 'entity.valid_from') if body.get('valid_from') else None
        valid_to = canonical_time(body['valid_to'], 'entity.valid_to') if body.get('valid_to') else None
        if valid_from and valid_to and parse_canonical(valid_to) < parse_canonical(valid_from):
            raise Problem('VALIDATION_ERROR', 'Entity valid_to 不能早于 valid_from。', 422)
        return {**body, 'canonical_name': canonical_name, 'aliases': aliases, 'valid_from': valid_from, 'valid_to': valid_to}

    @staticmethod
    def _normalize_relation_input(body):
        occurred_at = canonical_time(body['occurred_at'], 'relation.occurred_at')
        valid_from = canonical_time(body['valid_from'], 'relation.valid_from') if body.get('valid_from') else None
        valid_to = canonical_time(body['valid_to'], 'relation.valid_to') if body.get('valid_to') else None
        if body['subject_entity_id'] == body['object_entity_id']:
            raise Problem('MEMORY_GRAPH_REJECTED', 'M3-A 不允许自环 Relation。', 422)
        if valid_from and valid_to and parse_canonical(valid_to) < parse_canonical(valid_from):
            raise Problem('VALIDATION_ERROR', 'Relation valid_to 不能早于 valid_from。', 422)
        return {**body, 'occurred_at': occurred_at, 'valid_from': valid_from, 'valid_to': valid_to}

    def create_entity(self, bank_id, body, key):
        validate_graph_contract('entity_input', body)
        entity_input = self._normalize_entity_input(body)

        def create(db):
            self._bank(db, bank_id)
            self._active_support_fact(db, bank_id, entity_input['support_fact_id'])
            name_key = entity_input['entity_type'] + ':' + entity_input['canonical_name'].casefold()
            existing_rows = db.execute('SELECT doc FROM memory_entities WHERE bank_id=? AND canonical_key=?',
                                       (bank_id, name_key)).fetchall()
            for row in existing_rows:
                existing = json.loads(row['doc'])
                if existing['status'] == 'active':
                    if (existing['support_fact_id'] == entity_input['support_fact_id'] and
                            existing['aliases'] == entity_input['aliases'] and
                            existing['valid_from'] == entity_input['valid_from'] and
                            existing['valid_to'] == entity_input['valid_to']):
                        return {'entity': self._graph_entity_view(existing), 'deduplicated': True, 'audit_id': None}
                    raise Problem('MEMORY_GRAPH_ENTITY_EXISTS', '同 Bank 已有同类型、同规范名称的 active Entity。', 409)
            entity = {
                'id': uid('mement'), 'bank_id': bank_id, 'canonical_name': entity_input['canonical_name'],
                'entity_type': entity_input['entity_type'], 'aliases': entity_input['aliases'],
                'support_fact_id': entity_input['support_fact_id'], 'valid_from': entity_input['valid_from'],
                'valid_to': entity_input['valid_to'], 'status': 'active', 'recorded_at': now(),
            }
            validate_graph_contract('entity', entity)
            db.execute('INSERT INTO memory_entities VALUES(?,?,?,?)', (entity['id'], bank_id, name_key, dumps(entity)))
            audit = self._audit(db, bank_id, 'memory.entity.retained', entity['id'], {
                'entity_type': entity['entity_type'], 'canonical_name_sha256': digest(entity['canonical_name'].encode()),
                'support_fact_id': entity['support_fact_id'], 'alias_count': len(entity['aliases']),
            })
            return {'entity': self._graph_entity_view(entity), 'deduplicated': False, 'audit_id': audit['id']}

        return self._idempotent('memory:entities:' + bank_id, key, entity_input, create)

    def _active_entity_in_transaction(self, db, bank_id, entity_id, point=None):
        point = point or parse_canonical(now())
        row = db.execute('SELECT doc FROM memory_entities WHERE id=? AND bank_id=?', (entity_id, bank_id)).fetchone()
        if not row:
            raise Problem('MEMORY_GRAPH_ENTITY_NOT_FOUND', 'Graph Entity 不在此 Memory Bank。', 404)
        entity = json.loads(row['doc'])
        if entity['status'] != 'active' or not self._within_window(entity, point):
            raise Problem('MEMORY_GRAPH_ENTITY_NOT_ACTIVE', 'Graph Entity 当前无效。', 409)
        self._active_support_fact(db, bank_id, entity['support_fact_id'], point)
        return entity

    def create_relation(self, bank_id, body, key):
        validate_graph_contract('relation_input', body)
        relation_input = self._normalize_relation_input(body)

        def create(db):
            self._bank(db, bank_id)
            point = parse_canonical(now())
            self._active_entity_in_transaction(db, bank_id, relation_input['subject_entity_id'], point)
            self._active_entity_in_transaction(db, bank_id, relation_input['object_entity_id'], point)
            self._active_support_fact(db, bank_id, relation_input['support_fact_id'], point)
            existing_rows = db.execute(
                'SELECT doc FROM memory_relations WHERE bank_id=? AND subject_entity_id=? AND object_entity_id=?',
                (bank_id, relation_input['subject_entity_id'], relation_input['object_entity_id'])).fetchall()
            for row in existing_rows:
                existing = json.loads(row['doc'])
                if existing['status'] == 'active' and all(existing[name] == relation_input[name] for name in (
                        'predicate', 'support_fact_id', 'confidence', 'occurred_at', 'valid_from', 'valid_to')):
                    return {'relation': self._graph_relation_view(existing), 'deduplicated': True, 'audit_id': None}
            relation = {
                'id': uid('memrel'), 'bank_id': bank_id, 'subject_entity_id': relation_input['subject_entity_id'],
                'predicate': relation_input['predicate'], 'object_entity_id': relation_input['object_entity_id'],
                'support_fact_id': relation_input['support_fact_id'], 'confidence': relation_input['confidence'],
                'occurred_at': relation_input['occurred_at'], 'valid_from': relation_input['valid_from'],
                'valid_to': relation_input['valid_to'], 'status': 'active', 'recorded_at': now(),
            }
            validate_graph_contract('relation', relation)
            db.execute('INSERT INTO memory_relations VALUES(?,?,?,?,?)',
                       (relation['id'], bank_id, relation['subject_entity_id'], relation['object_entity_id'], dumps(relation)))
            audit = self._audit(db, bank_id, 'memory.relation.retained', relation['id'], {
                'predicate': relation['predicate'], 'subject_entity_id': relation['subject_entity_id'],
                'object_entity_id': relation['object_entity_id'], 'support_fact_id': relation['support_fact_id'],
            })
            return {'relation': self._graph_relation_view(relation), 'deduplicated': False, 'audit_id': audit['id']}

        return self._idempotent('memory:relations:' + bank_id, key, relation_input, create)

    def _active_graph_documents(self, bank_id, point):
        with self.store.lock:
            source_rows = self.store.db.execute('SELECT doc FROM memory_sources WHERE bank_id=?', (bank_id,)).fetchall()
            fact_rows = self.store.db.execute('SELECT doc FROM memory_facts WHERE bank_id=?', (bank_id,)).fetchall()
            entity_rows = self.store.db.execute('SELECT doc FROM memory_entities WHERE bank_id=?', (bank_id,)).fetchall()
            relation_rows = self.store.db.execute('SELECT doc FROM memory_relations WHERE bank_id=?', (bank_id,)).fetchall()
        sources = {source['id']: source for row in source_rows if (source := json.loads(row['doc']))['status'] == 'active'
                   and parse_canonical(source['occurred_at']) <= point and parse_canonical(source['expires_at']) >= point}
        facts = {fact['id']: fact for row in fact_rows if (fact := json.loads(row['doc']))['status'] == 'active'
                 and fact['source_id'] in sources and self._within_window(fact, point)}
        entities = {entity['id']: entity for row in entity_rows if (entity := json.loads(row['doc']))['status'] == 'active'
                    and entity['support_fact_id'] in facts and self._within_window(entity, point)}
        relations = {relation['id']: relation for row in relation_rows if (relation := json.loads(row['doc']))['status'] == 'active'
                     and relation['support_fact_id'] in facts and relation['subject_entity_id'] in entities
                     and relation['object_entity_id'] in entities and self._within_window(relation, point)}
        return sources, facts, entities, relations

    @staticmethod
    def _graph_node(entity):
        return {'entity_id': entity['id'], 'canonical_name': entity['canonical_name'],
                'entity_type': entity['entity_type'], 'support_fact_id': entity['support_fact_id']}

    @staticmethod
    def _graph_edge(relation, fact, source, direction):
        return {
            'relation_id': relation['id'], 'subject_entity_id': relation['subject_entity_id'],
            'predicate': relation['predicate'], 'object_entity_id': relation['object_entity_id'], 'direction': direction,
            'support_evidence': {'evidence_id': fact['id'], 'statement': fact['statement'], 'source_id': source['id'],
                                 'source_ref': source['source_ref'], 'content_sha256': source['content_sha256'],
                                 'occurred_at': fact['occurred_at']},
        }

    def graph_recall(self, bank_id, body):
        validate_graph_contract('graph_recall_request', body)
        bank = self.store.memory_bank(bank_id)
        as_of = canonical_time(body['as_of'], 'as_of') if body.get('as_of') else now()
        point = parse_canonical(as_of)
        sources, facts, entities, relations = self._active_graph_documents(bank['id'], point)
        start_id = body['start_entity_id']
        limit, max_hops = body.get('limit', 10), body.get('max_hops', 1)
        paths = []
        if start_id in entities:
            queue = [(start_id, [start_id], [])]
            ordered = sorted(relations.values(), key=lambda item: (item['occurred_at'], item['id']), reverse=True)
            while queue and len(paths) < limit:
                current_id, node_ids, edges = queue.pop(0)
                if len(edges) >= max_hops:
                    continue
                for relation in ordered:
                    if relation['subject_entity_id'] == current_id:
                        next_id, direction = relation['object_entity_id'], 'outgoing'
                    elif relation['object_entity_id'] == current_id:
                        next_id, direction = relation['subject_entity_id'], 'incoming'
                    else:
                        continue
                    if next_id in node_ids:
                        continue
                    fact, source = facts[relation['support_fact_id']], sources[facts[relation['support_fact_id']]['source_id']]
                    next_nodes = [*node_ids, next_id]
                    next_edges = [*edges, self._graph_edge(relation, fact, source, direction)]
                    paths.append({'hop_count': len(next_edges), 'nodes': [self._graph_node(entities[node_id]) for node_id in next_nodes],
                                  'edges': next_edges})
                    if len(paths) >= limit:
                        break
                    if len(next_edges) < max_hops:
                        queue.append((next_id, next_nodes, next_edges))
        bundle = {
            'schema_version': 'graph-evidence-bundle@1', 'bank_id': bank['id'], 'start_entity_id': start_id, 'as_of': as_of,
            'memory_status': 'available' if paths else 'empty', 'channels': ['graph', 'temporal'], 'paths': paths,
            'safety': {'raw_source_content_included': False, 'model_calls': 0, 'automatic_entity_resolution': False},
        }
        validate_graph_contract('graph_evidence_bundle', bundle)
        return bundle

    def resolve_entity(self, bank_id, body):
        validate_entity_catalog_contract('entity_resolve_request', body)
        bank = self.store.memory_bank(bank_id)
        name = body['name'].strip()
        if not name or SENSITIVE_INPUT.search(name):
            raise Problem('MEMORY_ENTITY_CATALOG_REJECTED', 'Entity 查询名称为空或包含凭证样式内容。', 422)
        as_of = canonical_time(body['as_of'], 'as_of') if body.get('as_of') else now()
        sources, facts, entities, _ = self._active_graph_documents(bank['id'], parse_canonical(as_of))
        entity_type = body.get('entity_type')
        candidates = []
        for entity in entities.values():
            if entity_type and entity['entity_type'] != entity_type:
                continue
            matched_name = next((item for item in [entity['canonical_name'], *entity['aliases']]
                                 if item.casefold() == name.casefold()), None)
            if matched_name is None:
                continue
            fact = facts[entity['support_fact_id']]
            source = sources[fact['source_id']]
            candidates.append({
                'entity_id': entity['id'], 'canonical_name': entity['canonical_name'], 'entity_type': entity['entity_type'],
                'matched_name': matched_name,
                'support_evidence': {'evidence_id': fact['id'], 'statement': fact['statement'], 'source_id': source['id'],
                                     'source_ref': source['source_ref'], 'content_sha256': source['content_sha256'],
                                     'occurred_at': fact['occurred_at']},
            })
        candidates.sort(key=lambda item: (item['entity_type'], item['canonical_name'].casefold(), item['entity_id']))
        if len(candidates) > 16:
            raise Problem('MEMORY_ENTITY_CATALOG_AMBIGUOUS_LIMIT', '精确名称候选超过安全上限；请增加 entity_type 或改用已知 Entity ID。', 409)
        status = 'resolved' if len(candidates) == 1 else ('ambiguous' if candidates else 'not_found')
        result = {
            'schema_version': 'entity-resolution@1', 'bank_id': bank['id'], 'name': name, 'as_of': as_of,
            'status': status, 'candidates': candidates,
            'next_action': {'operation': 'memory.graph_recall@1', 'requires_explicit_entity_id': True},
            'safety': {'match_mode': 'exact_canonical_or_alias_casefold', 'automatic_entity_resolution': False,
                       'raw_source_content_included': False, 'model_calls': 0},
        }
        validate_entity_catalog_contract('entity_resolution', result)
        return result

    def _invalidate_graph_for_facts(self, db, bank_id, fact_ids, status):
        fact_ids = set(fact_ids)
        if not fact_ids:
            return {'entities': 0, 'relations': 0}
        entity_rows = db.execute('SELECT id,doc FROM memory_entities WHERE bank_id=?', (bank_id,)).fetchall()
        entity_ids = set()
        entities_changed = 0
        for row in entity_rows:
            entity = json.loads(row['doc'])
            if entity['status'] == 'active' and entity['support_fact_id'] in fact_ids:
                entity['status'] = status
                db.execute('UPDATE memory_entities SET doc=? WHERE id=?', (dumps(entity), entity['id']))
                entity_ids.add(entity['id'])
                entities_changed += 1
        relation_rows = db.execute('SELECT id,doc FROM memory_relations WHERE bank_id=?', (bank_id,)).fetchall()
        relations_changed = 0
        for row in relation_rows:
            relation = json.loads(row['doc'])
            if relation['status'] == 'active' and (relation['support_fact_id'] in fact_ids or
                                                   relation['subject_entity_id'] in entity_ids or
                                                   relation['object_entity_id'] in entity_ids):
                relation['status'] = status
                db.execute('UPDATE memory_relations SET doc=? WHERE id=?', (dumps(relation), relation['id']))
                relations_changed += 1
        return {'entities': entities_changed, 'relations': relations_changed}

    def _delete_graph_for_facts(self, db, bank_id, fact_ids):
        fact_ids = set(fact_ids)
        if not fact_ids:
            return {'entities': 0, 'relations': 0}
        entity_rows = db.execute('SELECT id,doc FROM memory_entities WHERE bank_id=?', (bank_id,)).fetchall()
        entity_ids = {row['id'] for row in entity_rows if json.loads(row['doc'])['support_fact_id'] in fact_ids}
        relation_rows = db.execute('SELECT id,doc FROM memory_relations WHERE bank_id=?', (bank_id,)).fetchall()
        relation_ids = {row['id'] for row in relation_rows if (relation := json.loads(row['doc']))['support_fact_id'] in fact_ids
                        or relation['subject_entity_id'] in entity_ids or relation['object_entity_id'] in entity_ids}
        if relation_ids:
            db.executemany('DELETE FROM memory_relations WHERE id=?', ((ident,) for ident in relation_ids))
        if entity_ids:
            db.executemany('DELETE FROM memory_entities WHERE id=?', ((ident,) for ident in entity_ids))
        return {'entities': len(entity_ids), 'relations': len(relation_ids)}

    def retract_source(self, source_id, key):
        def retract(db):
            source = self._source(db, source_id)
            if source['status'] == 'retracted':
                return {'source_id': source_id, 'status': 'retracted', 'retracted_fact_count': 0, 'already_retracted': True}
            if source['status'] != 'active':
                raise Problem('MEMORY_SOURCE_NOT_ACTIVE', '只能撤回 active Source。', 409)
            source['status'], source['retracted_at'] = 'retracted', now()
            db.execute('UPDATE memory_sources SET doc=? WHERE id=?', (dumps(source), source_id))
            rows = db.execute('SELECT id,doc FROM memory_facts WHERE source_id=?', (source_id,)).fetchall()
            changed, changed_fact_ids = 0, []
            for row in rows:
                fact = json.loads(row['doc'])
                if fact['status'] == 'active':
                    fact['status'] = 'retracted'
                    db.execute('UPDATE memory_facts SET doc=? WHERE id=?', (dumps(fact), fact['id']))
                    self._remove_index_entries(db, [fact['id']])
                    changed += 1
                    changed_fact_ids.append(fact['id'])
            graph_invalidated = self._invalidate_graph_for_facts(db, source['bank_id'], changed_fact_ids, 'retracted')
            audit = self._audit(db, source['bank_id'], 'memory.source.retracted', source_id, {
                'source_sha256': source['content_sha256'], 'retracted_fact_count': changed,
                'retracted_entity_count': graph_invalidated['entities'],
                'retracted_relation_count': graph_invalidated['relations'],
            })
            return {'source_id': source_id, 'status': 'retracted', 'retracted_fact_count': changed, 'already_retracted': False,
                    'retracted_entity_count': graph_invalidated['entities'],
                    'retracted_relation_count': graph_invalidated['relations'], 'audit_id': audit['id']}
        return self._idempotent('memory:retract:' + source_id, key, {}, retract)

    def delete_source(self, source_id, key):
        def delete(db):
            source = self._source(db, source_id)
            facts = db.execute('SELECT id FROM memory_facts WHERE source_id=?', (source_id,)).fetchall()
            graph_deleted = self._delete_graph_for_facts(db, source['bank_id'], [fact['id'] for fact in facts])
            tombstone = {
                'id': uid('memtomb'), 'bank_id': source['bank_id'], 'deleted_source_id': source_id,
                'source_sha256': source['content_sha256'], 'deleted_at': now(), 'deleted_fact_count': len(facts),
                'deleted_entity_count': graph_deleted['entities'], 'deleted_relation_count': graph_deleted['relations'],
                'reason': 'local_admin_delete',
            }
            self._remove_index_entries(db, [fact['id'] for fact in facts])
            db.execute('DELETE FROM memory_facts WHERE source_id=?', (source_id,))
            db.execute('DELETE FROM memory_sources WHERE id=?', (source_id,))
            db.execute('INSERT INTO memory_tombstones VALUES(?,?,?)', (tombstone['id'], source['bank_id'], dumps(tombstone)))
            audit = self._audit(db, source['bank_id'], 'memory.source.deleted', source_id, {
                'source_sha256': source['content_sha256'], 'deleted_fact_count': len(facts),
                'deleted_entity_count': graph_deleted['entities'], 'deleted_relation_count': graph_deleted['relations'],
                'tombstone_id': tombstone['id'],
            })
            return {'source_id': source_id, 'status': 'deleted', 'deleted_fact_count': len(facts),
                    'deleted_entity_count': graph_deleted['entities'], 'deleted_relation_count': graph_deleted['relations'],
                    'tombstone_id': tombstone['id'], 'audit_id': audit['id']}
        return self._idempotent('memory:delete:' + source_id, key, {}, delete)


def _source_view(source):
    return {key: source[key] for key in ('id', 'bank_id', 'source_ref', 'content_sha256', 'data_classification',
                                         'occurred_at', 'recorded_at', 'expires_at', 'status', 'retracted_at')}


def _fact_view(fact):
    return {key: fact[key] for key in ('id', 'bank_id', 'source_id', 'statement', 'kind', 'confidence', 'occurred_at',
                                       'valid_from', 'valid_to', 'status', 'supersedes_fact_id', 'superseded_by_fact_id', 'recorded_at')}
