"""Validated small workflow engine. No eval, arbitrary HTTP, or independent model budget."""
from __future__ import annotations

import asyncio
import copy
import json
import re
import time

from .analysis import Problem, digest
from .store import dumps, now, uid
from .support_providers import fail

KEY = re.compile(r'[a-z][a-z0-9_]{0,31}')
VARIABLE = re.compile(r'\{\{([a-z][a-z0-9_]{0,31}\.(?:output|input))\}\}')


def render(template, pool):
    def value(match):
        if match[1] not in pool:
            raise fail('SUPPORT_WORKFLOW_VARIABLE', 409)
        found = pool[match[1]]
        return found if isinstance(found, str) else dumps(found)
    result = VARIABLE.sub(value, template)
    if len(result) > 16000:
        raise fail('SUPPORT_WORKFLOW_OUTPUT_LIMIT', 409)
    return result


def definition(body):
    if (not isinstance(body, dict) or set(body) != {'name', 'description', 'enabled', 'nodes', 'edges'}
            or not isinstance(body['name'], str) or not 1 <= len(body['name'].strip()) <= 100
            or not isinstance(body['description'], str) or len(body['description']) > 500
            or type(body['enabled']) is not bool or not isinstance(body['nodes'], list) or not 2 <= len(body['nodes']) <= 32
            or not isinstance(body['edges'], list) or len(body['edges']) > 64):
        raise fail('SUPPORT_WORKFLOW_INVALID')
    nodes, outgoing = {}, {}
    for node in body['nodes']:
        if (not isinstance(node, dict) or set(node) != {'id', 'type', 'config'} or not isinstance(node['id'], str)
                or not KEY.fullmatch(node['id']) or node['id'] in nodes or not isinstance(node['config'], dict)):
            raise fail('SUPPORT_WORKFLOW_INVALID')
        kind, config = node['type'], node['config']
        fields = {'START': set(), 'LLM': {'prompt'}, 'CONDITION': {'left', 'operator', 'right'},
                  'KNOWLEDGE': {'kb_id', 'query', 'top_k'}, 'TOOL': {'name', 'arguments'}, 'END': {'text'}}
        if not isinstance(kind, str) or kind not in fields or set(config) != fields[kind]:
            raise fail('SUPPORT_WORKFLOW_INVALID')
        for k, v in config.items():
            if k == 'top_k':
                if type(v) is not int or not 1 <= v <= 4: raise fail('SUPPORT_WORKFLOW_INVALID')
            elif k == 'arguments':
                if not isinstance(v, dict) or len(dumps(v)) > 4000: raise fail('SUPPORT_WORKFLOW_INVALID')
            elif not isinstance(v, str) or len(v) > 8000:
                raise fail('SUPPORT_WORKFLOW_INVALID')
        if kind == 'CONDITION' and config['operator'] not in {'equals', 'not_equals', 'contains'}:
            raise fail('SUPPORT_WORKFLOW_INVALID')
        nodes[node['id']], outgoing[node['id']] = node, []
    starts = [n['id'] for n in nodes.values() if n['type'] == 'START']
    if len(starts) != 1 or starts[0] != 'start' or not any(n['type'] == 'END' for n in nodes.values()):
        raise fail('SUPPORT_WORKFLOW_INVALID')
    for edge in body['edges']:
        if (not isinstance(edge, dict) or set(edge) != {'source', 'target', 'condition'}
                or not isinstance(edge['source'], str) or edge['source'] not in nodes
                or not isinstance(edge['target'], str) or edge['target'] not in nodes
                or edge['condition'] is not None and type(edge['condition']) is not bool):
            raise fail('SUPPORT_WORKFLOW_INVALID')
        outgoing[edge['source']].append(edge)
    for key, node in nodes.items():
        edges = outgoing[key]
        if node['type'] == 'END': valid = not edges
        elif node['type'] == 'CONDITION': valid = len(edges) == 2 and {e['condition'] for e in edges} == {True, False}
        else: valid = len(edges) == 1 and edges[0]['condition'] is None
        if not valid: raise fail('SUPPORT_WORKFLOW_INVALID')
    visited, active = set(), set()
    def walk(key):
        if key in active: raise fail('SUPPORT_WORKFLOW_CYCLE')
        if key in visited: return
        active.add(key)
        for edge in outgoing[key]: walk(edge['target'])
        active.remove(key)
        visited.add(key)
    walk('start')
    if visited != set(nodes): raise fail('SUPPORT_WORKFLOW_UNREACHABLE')
    return copy.deepcopy(body)


class SupportWorkflows:
    def __init__(self, store, providers):
        self.store, self.providers = store, providers
        with store.lock:
            store.db.executescript('''
                CREATE TABLE IF NOT EXISTS support_workflows(id TEXT PRIMARY KEY, doc TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS support_workflow_runs(id TEXT PRIMARY KEY, workflow_id TEXT NOT NULL, doc TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS support_workflow_steps(id TEXT PRIMARY KEY, run_id TEXT NOT NULL, doc TEXT NOT NULL);
            ''')
        self.recover()

    def get(self, ident, *, enabled=False):
        with self.store.lock:
            row = self.store.db.execute('SELECT doc FROM support_workflows WHERE id=?', (ident,)).fetchone()
            if not row: raise fail('SUPPORT_WORKFLOW_NOT_FOUND', 404)
            doc = json.loads(row[0])
            if enabled and not doc['enabled']: raise fail('SUPPORT_WORKFLOW_DISABLED', 409)
            return doc

    def listing(self):
        with self.store.lock:
            return [json.loads(r[0]) for r in self.store.db.execute('SELECT doc FROM support_workflows ORDER BY rowid DESC LIMIT 100')]

    def save(self, body, ident=None):
        self.providers.require_enabled()
        if not isinstance(body, dict) or set(body) - {'name', 'description', 'enabled', 'nodes', 'edges'}:
            raise fail('SUPPORT_WORKFLOW_INVALID')
        with self.store.transaction() as db:
            old = self.get(ident) if ident else {}
            doc = definition({k: body.get(k, old.get(k, v)) for k, v in
                              {'name': '', 'description': '', 'enabled': True, 'nodes': [], 'edges': []}.items()})
            if not ident and db.execute('SELECT count(*) FROM support_workflows').fetchone()[0] >= 100:
                raise fail('SUPPORT_WORKFLOW_LIMIT', 409)
            doc.update(id=ident or uid('csw'), revision=digest(dumps(doc).encode()), created_at=old.get('created_at', now()), updated_at=now())
            db.execute('INSERT INTO support_workflows VALUES(?,?) ON CONFLICT(id) DO UPDATE SET doc=excluded.doc', (doc['id'], dumps(doc)))
        return doc

    def delete(self, ident):
        with self.store.transaction() as db:
            self.get(ident)
            db.execute('DELETE FROM support_workflows WHERE id=?', (ident,))
        return {'deleted': True}  # Historical execution receipts remain readable.

    def validate_current(self, frozen):
        doc = self.get(frozen['id'], enabled=True)
        if doc['revision'] != frozen['revision']:
            raise fail('SUPPORT_WORKFLOW_CHANGED', 409)

    def runs(self, ident):
        with self.store.lock:
            runs = [json.loads(r[0]) for r in self.store.db.execute('SELECT doc FROM support_workflow_runs WHERE workflow_id=? ORDER BY rowid DESC LIMIT 50', (ident,))]
            for run in runs:
                run['steps'] = [json.loads(r[0]) for r in self.store.db.execute('SELECT doc FROM support_workflow_steps WHERE run_id=? ORDER BY rowid', (run['id'],))]
            return runs

    def finish(self, db, ident, status, code=None):
        row = db.execute('SELECT doc FROM support_workflow_runs WHERE id=?', (ident,)).fetchone()
        if row:
            doc = json.loads(row[0])
            if doc['status'] in {'running', 'awaiting_publication'}:
                doc.update(status=status, error_code=code, finished_at=now())
                db.execute('UPDATE support_workflow_runs SET doc=? WHERE id=?', (dumps(doc), ident))

    def recover(self):
        with self.store.transaction() as db:
            for row in db.execute('SELECT id FROM support_workflow_runs').fetchall():
                self.finish(db, row[0], 'failed', 'SUPPORT_RESTARTED')
            for row in db.execute("SELECT id,doc FROM support_workflow_steps WHERE json_extract(doc,'$.status')='running'").fetchall():
                doc = json.loads(row['doc'])
                doc.update(status='failed', error_code='SUPPORT_RESTARTED')
                db.execute('UPDATE support_workflow_steps SET doc=? WHERE id=?', (dumps(doc), row['id']))

    async def execute(self, frozen, *, run_id, user_input, ask, retrieve, tool, notify, check, cancel, deadline):
        self.validate_current(frozen)
        node_map = {n['id']: n for n in frozen['nodes']}
        pool, current = {'start.input': user_input}, 'start'
        with self.store.transaction() as db:
            db.execute('INSERT INTO support_workflow_runs VALUES(?,?,?)', (run_id, frozen['id'], dumps({
                'id': run_id, 'workflow_id': frozen['id'], 'revision': frozen['revision'], 'status': 'running',
                'created_at': now(), 'input_sha256': digest(user_input.encode()), 'error_code': None})))
        for sequence in range(32):
            check()
            self.validate_current(frozen)
            node = node_map[current]
            step = {'id': uid('cwn'), 'node': current, 'type': node['type'], 'sequence': sequence,
                    'status': 'running', 'created_at': now()}
            with self.store.transaction() as db:
                db.execute('INSERT INTO support_workflow_steps VALUES(?,?,?)', (step['id'], run_id, dumps(step)))
            started = time.monotonic()
            async def execute_node():
                config, kind = node['config'], node['type']
                if kind == 'START': return user_input
                if kind == 'LLM':
                    prompt = render(config['prompt'], pool)
                    step['input_sha256'] = digest(prompt.encode())
                    return await ask(prompt)
                if kind == 'KNOWLEDGE': return await retrieve(config['kb_id'], render(config['query'], pool), config['top_k'])
                if kind == 'TOOL':
                    def expand(value):
                        if isinstance(value, str): return render(value, pool)
                        if isinstance(value, list): return [expand(i) for i in value]
                        if isinstance(value, dict): return {k: expand(v) for k, v in value.items()}
                        return value
                    arguments = expand(config['arguments'])
                    step['input_sha256'] = digest(dumps(arguments).encode())
                    return await tool(config['name'], arguments)
                if kind == 'CONDITION':
                    left, right = render(config['left'], pool), render(config['right'], pool)
                    return left == right if config['operator'] == 'equals' else left != right if config['operator'] == 'not_equals' else right in left
                if kind == 'END': return render(config['text'], pool)
                raise fail('SUPPORT_WORKFLOW_INVALID')
            operation, interrupted = asyncio.create_task(execute_node()), asyncio.create_task(cancel.wait())
            try:
                await notify({'type': 'workflow', 'node': current, 'state': 'running'})
                await asyncio.wait({operation, interrupted}, timeout=max(0, deadline-time.monotonic()), return_when=asyncio.FIRST_COMPLETED)
                check()
                if not operation.done(): raise TimeoutError()
                output = operation.result()
                if len(dumps(output)) > 16000 or sum(len(dumps(v)) for v in pool.values()) + len(dumps(output)) > 64000:
                    raise fail('SUPPORT_WORKFLOW_OUTPUT_LIMIT', 409)
                if current+'.output' in pool: raise fail('SUPPORT_WORKFLOW_CYCLE', 409)
                pool[current+'.output'] = output
                step.update(status='succeeded', output_sha256=digest(dumps(output).encode()), output_chars=len(dumps(output)))
            except BaseException as exc:
                step.update(status='cancelled' if isinstance(exc, asyncio.CancelledError) else 'failed',
                    error_code=exc.code if isinstance(exc, Problem) else 'SUPPORT_WORKFLOW_INTERRUPTED')
                raise
            finally:
                for task in (operation, interrupted):
                    if not task.done(): task.cancel()
                await asyncio.gather(operation, interrupted, return_exceptions=True)
                step['elapsed_ms'] = round((time.monotonic()-started)*1000)
                with self.store.transaction() as db:
                    db.execute('UPDATE support_workflow_steps SET doc=? WHERE id=?', (dumps(step), step['id']))
            await notify({'type': 'workflow', 'node': current, 'state': 'succeeded'})
            if node['type'] == 'END':
                if not isinstance(output, str) or not output.strip(): raise fail('SUPPORT_WORKFLOW_EMPTY', 409)
                with self.store.transaction() as db:
                    self.finish(db, run_id, 'awaiting_publication')
                return output
            edges = [e for e in frozen['edges'] if e['source'] == current and
                     (e['condition'] is output if node['type'] == 'CONDITION' else e['condition'] is None)]
            if len(edges) != 1: raise fail('SUPPORT_WORKFLOW_BRANCH', 409)
            current = edges[0]['target']
        raise fail('SUPPORT_WORKFLOW_STEP_LIMIT', 409)
