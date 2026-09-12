"""Single-process SQLite transaction boundary; every state change owns its events."""
import json
import sqlite3
import threading
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

from .analysis import Problem


def now():
    return datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')


def uid(prefix):
    return prefix + '_' + uuid.uuid4().hex


def dumps(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, allow_nan=False)


class Store:
    def __init__(self, path):
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.lock = threading.RLock()
        self.db = sqlite3.connect(path, check_same_thread=False, isolation_level=None)
        self.db.row_factory = sqlite3.Row
        self.db.execute('PRAGMA journal_mode=WAL')
        self.db.execute('PRAGMA foreign_keys=ON')
        self.db.executescript('''
            CREATE TABLE IF NOT EXISTS resources(id TEXT PRIMARY KEY, doc TEXT NOT NULL, raw BLOB NOT NULL);
            CREATE TABLE IF NOT EXISTS tasks(id TEXT PRIMARY KEY, doc TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS runs(id TEXT PRIMARY KEY, task_id TEXT NOT NULL REFERENCES tasks(id), doc TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS events(run_id TEXT REFERENCES runs(id), sequence INTEGER, doc TEXT NOT NULL, PRIMARY KEY(run_id,sequence));
            CREATE TABLE IF NOT EXISTS artifacts(id TEXT PRIMARY KEY, run_id TEXT REFERENCES runs(id), doc TEXT NOT NULL, body BLOB NOT NULL);
            CREATE TABLE IF NOT EXISTS idempotency(scope TEXT, key TEXT, digest TEXT NOT NULL, response TEXT NOT NULL, PRIMARY KEY(scope,key));
        ''')

    @contextmanager
    def transaction(self):
        with self.lock:
            self.db.execute('BEGIN IMMEDIATE')
            try:
                yield self.db
                self.db.execute('COMMIT')
            except BaseException:
                self.db.execute('ROLLBACK')
                raise

    def get(self, table, ident):
        if table not in ('resources', 'tasks', 'runs', 'artifacts'):
            raise ValueError('Unknown table')
        with self.lock:
            row = self.db.execute(f'SELECT doc FROM {table} WHERE id=?', (ident,)).fetchone()
        if not row:
            raise Problem('NOT_FOUND', '对象不存在。', 404)
        return json.loads(row['doc'])

    def listing(self, table):
        if table not in ('resources', 'tasks', 'runs'):
            raise ValueError('Unknown table')
        with self.lock:
            return [json.loads(r[0]) for r in self.db.execute(f'SELECT doc FROM {table} ORDER BY rowid DESC')]

    def event(self, db, run, kind, data=None, step_id=None):
        run['latest_sequence'] += 1
        run['updated_at'] = now()
        task = self.get('tasks', run['task_id'])
        event = {'event_id': uid('evt'), 'event_type': kind, 'event_version': 1,
                 'workspace_id': 'ws_local', 'project_id': task['project_id'], 'task_id': run['task_id'],
                 'run_id': run['id'], 'sequence': run['latest_sequence'], 'occurred_at': now(),
                 'trace_id': 'trace_' + (run.get('parent_run_id') or run['id'])[4:], 'step_id': step_id, 'data': data or {}}
        db.execute('INSERT INTO events VALUES(?,?,?)', (run['id'], event['sequence'], dumps(event)))
        db.execute('UPDATE runs SET doc=? WHERE id=?', (dumps(run), run['id']))

    def events(self, run_id, after=0):
        self.get('runs', run_id)
        with self.lock:
            return [json.loads(r[0]) for r in self.db.execute('SELECT doc FROM events WHERE run_id=? AND sequence>? ORDER BY sequence LIMIT 500', (run_id, after))]

    def artifact_list(self, run_id):
        self.get('runs', run_id)
        with self.lock:
            return [json.loads(r[0]) for r in self.db.execute('SELECT doc FROM artifacts WHERE run_id=? ORDER BY rowid', (run_id,))]

    def raw(self, resource_id):
        self.get('resources', resource_id)
        with self.lock:
            return self.db.execute('SELECT raw FROM resources WHERE id=?', (resource_id,)).fetchone()[0]

    def close(self):
        self.db.close()
