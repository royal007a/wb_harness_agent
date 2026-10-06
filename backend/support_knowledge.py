"""Small, local semantic knowledge library: bounded indexing and source-bound RAG."""
from __future__ import annotations

import asyncio
import json
import math
import os
from pathlib import Path
import sys

from .adaptive_retrieval import build_parent_child_chunks
from .analysis import Problem, digest
from .store import dumps, now, uid
from .support_providers import fail

MODEL = 'BAAI/bge-small-zh-v1.5@46fbe35fd4374a00fee7de77dfddaeb6dd6a2c59'
DIM = 512


def normalize(vector):
    if (not isinstance(vector, list) or len(vector) != DIM
            or any(type(v) not in (int, float) or not math.isfinite(v) for v in vector)):
        raise fail('SUPPORT_EMBEDDING_INVALID', 502)
    norm = math.sqrt(sum(v * v for v in vector))
    if not math.isfinite(norm) or norm < 1e-12:
        raise fail('SUPPORT_EMBEDDING_INVALID', 502)
    return [v / norm for v in vector]


class LocalEmbedding:
    def __init__(self):
        self.gate = asyncio.Semaphore(2)

    async def __call__(self, texts):
        root = os.environ.get('HARNESS_SUPPORT_EMBEDDING_DIR', '')
        if not root or not (Path(root) / 'support-model.json').is_file():
            raise fail('SUPPORT_EMBEDDING_NOT_READY', 409)
        # No API keys, startup injection flags, or proxy settings reach this worker.
        env = {'PATH': '/usr/bin:/bin', 'HF_HUB_OFFLINE': '1', 'HF_HUB_DISABLE_TELEMETRY': '1',
               'TOKENIZERS_PARALLELISM': 'false', 'PYTHONIOENCODING': 'utf-8'}
        async with self.gate:
            process = await asyncio.create_subprocess_exec(sys.executable,
                str(Path(__file__).with_name('support_embedding_worker.py')), root, env=env,
                stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL)
            async def communicate():
                process.stdin.write(dumps(texts).encode())
                await process.stdin.drain()
                process.stdin.close()
                chunks, count = [], 0
                while chunk := await process.stdout.read(65536):
                    count += len(chunk)
                    if count > 8 * 1024 * 1024:
                        raise fail('SUPPORT_EMBEDDING_LIMIT', 502)
                    chunks.append(chunk)
                await process.wait()
                if process.returncode:
                    raise fail('SUPPORT_EMBEDDING_FAILED', 502)
                try:
                    vectors = json.loads(b''.join(chunks))
                    if not isinstance(vectors, list) or len(vectors) != len(texts):
                        raise ValueError()
                    return [normalize(v) for v in vectors]
                except (ValueError, TypeError):
                    raise fail('SUPPORT_EMBEDDING_INVALID', 502) from None
            try:
                return await asyncio.wait_for(communicate(), 90)
            finally:
                if process.returncode is None:
                    process.kill()
                await process.wait()


class SupportKnowledge:
    def __init__(self, store, providers):
        self.store, self.providers = store, providers
        self.embed = LocalEmbedding()
        self.jobs = {}
        with store.lock:
            store.db.executescript('''
                CREATE TABLE IF NOT EXISTS support_knowledge(id TEXT PRIMARY KEY, doc TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS support_documents(id TEXT PRIMARY KEY, kb_id TEXT NOT NULL,
                    doc TEXT NOT NULL, source TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS support_chunks(id TEXT PRIMARY KEY, document_id TEXT NOT NULL,
                    kb_id TEXT NOT NULL, doc TEXT NOT NULL, vector TEXT NOT NULL);
                CREATE INDEX IF NOT EXISTS support_chunks_kb ON support_chunks(kb_id);
            ''')
        self.recover()

    def _row(self, table, ident):
        with self.store.lock:
            row = self.store.db.execute(f'SELECT * FROM {table} WHERE id=?', (ident,)).fetchone()
            if row is None:
                raise fail('SUPPORT_KNOWLEDGE_NOT_FOUND', 404)
            return row

    def get(self, ident, *, enabled=False):
        doc = json.loads(self._row('support_knowledge', ident)['doc'])
        if enabled and not doc['enabled']:
            raise fail('SUPPORT_KNOWLEDGE_DISABLED', 409)
        return doc

    def listing(self):
        with self.store.lock:
            return [json.loads(r[0]) for r in self.store.db.execute('SELECT doc FROM support_knowledge ORDER BY rowid DESC LIMIT 100')]

    def save(self, body, ident=None):
        self.providers.require_enabled()
        if not isinstance(body, dict) or set(body) - {'name', 'description', 'enabled'}:
            raise fail('SUPPORT_KNOWLEDGE_INVALID')
        with self.store.transaction() as db:
            old = self.get(ident) if ident else {}
            doc = {k: body.get(k, old.get(k, v)) for k, v in {'name': '', 'description': '', 'enabled': True}.items()}
            if (not isinstance(doc['name'], str) or not 1 <= len(doc['name'].strip()) <= 100
                    or not isinstance(doc['description'], str) or len(doc['description']) > 500 or type(doc['enabled']) is not bool):
                raise fail('SUPPORT_KNOWLEDGE_INVALID')
            if not ident and db.execute('SELECT count(*) FROM support_knowledge').fetchone()[0] >= 100:
                raise fail('SUPPORT_KNOWLEDGE_LIMIT', 409)
            doc.update(id=ident or uid('csk'), model=MODEL, dimension=DIM,
                       created_at=old.get('created_at', now()), updated_at=now())
            db.execute('INSERT INTO support_knowledge VALUES(?,?) ON CONFLICT(id) DO UPDATE SET doc=excluded.doc', (doc['id'], dumps(doc)))
        return doc

    def detail(self, ident):
        with self.store.lock:
            return {'knowledge': self.get(ident), 'documents': [json.loads(r[0]) for r in self.store.db.execute(
                'SELECT doc FROM support_documents WHERE kb_id=? ORDER BY rowid DESC', (ident,))]}

    def document(self, ident):
        with self.store.lock:
            doc = json.loads(self._row('support_documents', ident)['doc'])
            chunks = [json.loads(r[0]) for r in self.store.db.execute('SELECT doc FROM support_chunks WHERE document_id=? ORDER BY rowid', (ident,))]
        return {'document': doc, 'chunks': chunks}

    def delete(self, ident, *, document=False):
        with self.store.transaction() as db:
            if document:
                self._row('support_documents', ident)
                ids = [ident]
            else:
                self.get(ident)
                ids = [r[0] for r in db.execute('SELECT id FROM support_documents WHERE kb_id=?', (ident,))]
            if any(i in self.jobs and not self.jobs[i].done() for i in ids):
                raise fail('SUPPORT_DOCUMENT_BUSY', 409)
            for i in ids:
                db.execute('DELETE FROM support_chunks WHERE document_id=?', (i,))
                db.execute('DELETE FROM support_documents WHERE id=?', (i,))
            if not document:
                db.execute('DELETE FROM support_knowledge WHERE id=?', (ident,))
        return {'deleted': True}

    async def upload(self, ident, body):
        self.providers.require_enabled()
        if (not isinstance(body, dict) or set(body) != {'name', 'text'}
                or not isinstance(body['name'], str) or not 1 <= len(body['name'].strip()) <= 200
                or not isinstance(body['text'], str) or not body['text'].strip() or len(body['text']) > 100000):
            raise fail('SUPPORT_DOCUMENT_INVALID')
        if len([j for j in self.jobs.values() if not j.done()]) >= 8:
            raise fail('SUPPORT_INDEX_BUSY', 429)
        try:
            body['text'].encode('utf-8', 'strict')
        except UnicodeError:
            raise fail('SUPPORT_DOCUMENT_INVALID') from None
        source = body['text'].replace('\r\n', '\n').replace('\r', '\n')
        doc = {'id': uid('csd'), 'kb_id': ident, 'name': body['name'], 'status': 'processing', 'error_code': None,
               'sha256': digest(source.encode()), 'model': MODEL, 'dimension': DIM, 'chunk_count': 0, 'created_at': now()}
        with self.store.transaction() as db:
            self.get(ident, enabled=True)
            if db.execute('SELECT count(*) FROM support_documents WHERE kb_id=?', (ident,)).fetchone()[0] >= 100:
                raise fail('SUPPORT_KNOWLEDGE_LIMIT', 409)
            db.execute('INSERT INTO support_documents VALUES(?,?,?,?)', (doc['id'], ident, dumps(doc), source))
        task = asyncio.create_task(self._index(doc['id']))
        self.jobs[doc['id']] = task
        task.add_done_callback(lambda _: self.jobs.pop(doc['id'], None))
        return doc

    async def _index(self, ident):
        doc = None
        try:
            row = self._row('support_documents', ident)
            doc = json.loads(row['doc'])
            parts = build_parent_child_chunks(row['source'], max_child_chars=400, parent_max_chars=2000)
            if not parts['children'] or len(parts['children']) > 256:
                raise fail('SUPPORT_CHUNK_LIMIT', 422)
            vectors = await self.embed([c['text'] for c in parts['children']])
            if len(vectors) != len(parts['children']):
                raise fail('SUPPORT_EMBEDDING_INVALID', 502)
            vectors = [normalize(v) for v in vectors]
            parents = {p['id']: p for p in parts['parents']}
            with self.store.transaction() as db:
                self._row('support_documents', ident)
                self.get(doc['kb_id'])
                if db.execute('SELECT count(*) FROM support_chunks').fetchone()[0] + len(vectors) > 4000:
                    raise fail('SUPPORT_CHUNK_LIMIT', 409)
                for child, vector in zip(parts['children'], vectors):
                    chunk_id = ident + '_' + child['id']
                    chunk = {'id': chunk_id, 'document_id': ident, 'kb_id': doc['kb_id'], 'text': child['text'],
                             'start': child['start'], 'end': child['end'], 'parent': parents[child['parent_id']], 'model': MODEL}
                    db.execute('INSERT INTO support_chunks VALUES(?,?,?,?,?)',
                               (chunk_id, ident, doc['kb_id'], dumps(chunk), dumps(vector)))
                doc.update(status='ready', chunk_count=len(vectors))
                db.execute('UPDATE support_documents SET doc=? WHERE id=?', (dumps(doc), ident))
        except BaseException as exc:
            if doc is not None:
                doc.update(status='failed', error_code=exc.code if isinstance(exc, Problem) else 'SUPPORT_INDEX_INTERRUPTED'
                           if isinstance(exc, asyncio.CancelledError) else 'SUPPORT_INDEX_FAILED')
                with self.store.transaction() as db:
                    db.execute('UPDATE support_documents SET doc=? WHERE id=?', (dumps(doc), ident))
            if isinstance(exc, (asyncio.CancelledError, KeyboardInterrupt, SystemExit)):
                raise

    def recover(self):
        with self.store.transaction() as db:
            for row in db.execute("SELECT id,doc FROM support_documents WHERE json_extract(doc,'$.status')='processing'").fetchall():
                doc = json.loads(row['doc'])
                doc.update(status='failed', error_code='SUPPORT_INDEX_RESTARTED')
                db.execute('UPDATE support_documents SET doc=? WHERE id=?', (dumps(doc), row['id']))

    async def close(self):
        tasks = list(self.jobs.values())
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)

    async def search(self, kb_ids, query, *, top_k=3, min_score=.5):
        self.providers.require_enabled()
        if (not isinstance(query, str) or not 1 <= len(query.strip()) <= 2000 or type(top_k) is not int or not 1 <= top_k <= 8
                or type(min_score) not in (int, float) or not math.isfinite(min_score) or not 0 <= min_score <= 1
                or not isinstance(kb_ids, list) or not 1 <= len(kb_ids) <= 8 or len(set(kb_ids)) != len(kb_ids)):
            raise fail('SUPPORT_SEARCH_INVALID')
        for ident in kb_ids:
            self.get(ident, enabled=True)
        query_vector = normalize((await self.embed([query]))[0])
        candidates = []
        with self.store.lock:
            for ident in kb_ids:
                self.get(ident, enabled=True)
                rows = self.store.db.execute('''SELECT c.doc,c.vector,d.doc AS document FROM support_chunks c
                    JOIN support_documents d ON d.id=c.document_id WHERE c.kb_id=?''', (ident,)).fetchall()
                for row in rows:
                    chunk, document = json.loads(row['doc']), json.loads(row['document'])
                    if document['status'] != 'ready':
                        continue
                    if chunk['model'] != MODEL or document['model'] != MODEL:
                        raise fail('SUPPORT_EMBEDDING_VERSION', 409)
                    score = sum(a * b for a, b in zip(query_vector, normalize(json.loads(row['vector']))))
                    if score >= min_score:
                        candidates.append((score, chunk, document))
        result, used, chars = [], set(), 0
        for score, chunk, document in sorted(candidates, key=lambda v: (-v[0], v[1]['id'])):
            parent_key = (chunk['document_id'], chunk['parent']['id'])
            if parent_key in used:
                continue
            text = chunk['parent']['text']
            if chars + len(text) > 8000:
                continue
            used.add(parent_key)
            chars += len(text)
            result.append({'ref': chunk['id'], 'document_id': chunk['document_id'], 'kb_id': chunk['kb_id'],
                           'document_sha256': document['sha256'], 'name': document['name'],
                           'score': round(score, 6), 'text': text, 'start': chunk['parent']['start'], 'end': chunk['parent']['end']})
            if len(result) == top_k:
                break
        return {'items': result, 'engine': MODEL, 'dimension': DIM}

    def validate_sources(self, sources):
        for source in sources:
            self.get(source['kb_id'], enabled=True)
            doc = json.loads(self._row('support_documents', source['document_id'])['doc'])
            if doc['status'] != 'ready' or doc['sha256'] != source['document_sha256']:
                raise fail('SUPPORT_KNOWLEDGE_CHANGED', 409)
