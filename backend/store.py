"""Single-process SQLite transaction boundary; every state change owns its events."""
import json
import hmac
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
            CREATE TABLE IF NOT EXISTS checkpoints(id TEXT PRIMARY KEY, run_id TEXT NOT NULL REFERENCES runs(id), doc TEXT NOT NULL, state BLOB NOT NULL);
            CREATE TABLE IF NOT EXISTS control_evidence(id TEXT PRIMARY KEY, run_id TEXT NOT NULL REFERENCES runs(id), doc TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS control_gaps(id TEXT PRIMARY KEY, run_id TEXT NOT NULL REFERENCES runs(id), failure_event_id TEXT NOT NULL, doc TEXT NOT NULL, UNIQUE(run_id, failure_event_id));
            CREATE TABLE IF NOT EXISTS plan_revisions(id TEXT PRIMARY KEY, run_id TEXT NOT NULL REFERENCES runs(id), doc TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS replan_attempts(id TEXT PRIMARY KEY, origin_run_id TEXT NOT NULL REFERENCES runs(id), doc TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS idempotency(scope TEXT, key TEXT, digest TEXT NOT NULL, response TEXT NOT NULL, PRIMARY KEY(scope,key));
            CREATE TABLE IF NOT EXISTS oauth_attempts(id TEXT PRIMARY KEY, doc TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS provider_profiles(id TEXT PRIMARY KEY, doc TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS model_profiles(id TEXT PRIMARY KEY, provider_profile_id TEXT NOT NULL REFERENCES provider_profiles(id), doc TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS agent_profiles(id TEXT PRIMARY KEY, model_profile_id TEXT NOT NULL REFERENCES model_profiles(id), doc TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS chat_sessions(id TEXT PRIMARY KEY, agent_profile_id TEXT NOT NULL REFERENCES agent_profiles(id), doc TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS chat_messages(id TEXT PRIMARY KEY, session_id TEXT NOT NULL REFERENCES chat_sessions(id), sequence INTEGER NOT NULL, doc TEXT NOT NULL, UNIQUE(session_id, sequence));
            CREATE TABLE IF NOT EXISTS chat_exchanges(id TEXT PRIMARY KEY, session_id TEXT NOT NULL REFERENCES chat_sessions(id), idempotency_key TEXT NOT NULL, request_digest TEXT NOT NULL, doc TEXT NOT NULL, UNIQUE(session_id, idempotency_key));
            CREATE TABLE IF NOT EXISTS runtime_provider_profiles(id TEXT PRIMARY KEY, doc TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS runtime_model_profiles(id TEXT PRIMARY KEY, provider_profile_id TEXT NOT NULL REFERENCES runtime_provider_profiles(id), doc TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS runtime_agent_profiles(id TEXT PRIMARY KEY, model_profile_id TEXT NOT NULL REFERENCES runtime_model_profiles(id), doc TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS runtime_chat_sessions(id TEXT PRIMARY KEY, agent_profile_id TEXT NOT NULL REFERENCES runtime_agent_profiles(id), doc TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS runtime_chat_messages(id TEXT PRIMARY KEY, session_id TEXT NOT NULL REFERENCES runtime_chat_sessions(id), sequence INTEGER NOT NULL, doc TEXT NOT NULL, UNIQUE(session_id, sequence));
            CREATE TABLE IF NOT EXISTS runtime_chat_exchanges(id TEXT PRIMARY KEY, session_id TEXT NOT NULL REFERENCES runtime_chat_sessions(id), idempotency_key TEXT NOT NULL, request_digest TEXT NOT NULL, doc TEXT NOT NULL, UNIQUE(session_id, idempotency_key));
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

    def agent_lab_get(self, table, ident):
        if table not in ('provider_profiles', 'model_profiles', 'agent_profiles', 'chat_sessions', 'chat_messages', 'chat_exchanges'):
            raise ValueError('Unknown Agent Lab table')
        with self.lock:
            row = self.db.execute(f'SELECT doc FROM {table} WHERE id=?', (ident,)).fetchone()
        if not row:
            raise Problem('NOT_FOUND', '对象不存在。', 404)
        return json.loads(row['doc'])

    def agent_lab_listing(self, table):
        if table not in ('provider_profiles', 'model_profiles', 'agent_profiles', 'chat_sessions'):
            raise ValueError('Unknown Agent Lab table')
        with self.lock:
            rows = self.db.execute(f'SELECT doc FROM {table} ORDER BY rowid DESC').fetchall()
        return [json.loads(row['doc']) for row in rows]

    def chat_messages(self, session_id):
        self.agent_lab_get('chat_sessions', session_id)
        with self.lock:
            rows = self.db.execute('SELECT doc FROM chat_messages WHERE session_id=? ORDER BY sequence', (session_id,)).fetchall()
        return [json.loads(row['doc']) for row in rows]

    def chat_exchange(self, session_id, idempotency_key):
        with self.lock:
            row = self.db.execute('SELECT doc FROM chat_exchanges WHERE session_id=? AND idempotency_key=?',
                                  (session_id, idempotency_key)).fetchone()
        return json.loads(row['doc']) if row else None

    def runtime_get(self, table, ident):
        if table not in ('runtime_provider_profiles', 'runtime_model_profiles', 'runtime_agent_profiles',
                         'runtime_chat_sessions', 'runtime_chat_messages', 'runtime_chat_exchanges'):
            raise ValueError('Unknown runtime table')
        with self.lock:
            row = self.db.execute(f'SELECT doc FROM {table} WHERE id=?', (ident,)).fetchone()
        if not row:
            raise Problem('NOT_FOUND', '对象不存在。', 404)
        return json.loads(row['doc'])

    def runtime_listing(self, table):
        if table not in ('runtime_provider_profiles', 'runtime_model_profiles', 'runtime_agent_profiles', 'runtime_chat_sessions'):
            raise ValueError('Unknown runtime listing table')
        with self.lock:
            rows = self.db.execute(f'SELECT doc FROM {table} ORDER BY rowid DESC').fetchall()
        return [json.loads(row['doc']) for row in rows]

    def runtime_messages(self, session_id):
        self.runtime_get('runtime_chat_sessions', session_id)
        with self.lock:
            rows = self.db.execute('SELECT doc FROM runtime_chat_messages WHERE session_id=? ORDER BY sequence', (session_id,)).fetchall()
        return [json.loads(row['doc']) for row in rows]

    def runtime_exchange(self, session_id, idempotency_key):
        with self.lock:
            row = self.db.execute('SELECT doc FROM runtime_chat_exchanges WHERE session_id=? AND idempotency_key=?',
                                  (session_id, idempotency_key)).fetchone()
        return json.loads(row['doc']) if row else None

    def runtime_exchanges(self, session_id):
        self.runtime_get('runtime_chat_sessions', session_id)
        with self.lock:
            rows = self.db.execute('SELECT doc FROM runtime_chat_exchanges WHERE session_id=? ORDER BY rowid', (session_id,)).fetchall()
        return [json.loads(row['doc']) for row in rows]

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
        return event

    def events(self, run_id, after=0):
        self.get('runs', run_id)
        with self.lock:
            return [json.loads(r[0]) for r in self.db.execute('SELECT doc FROM events WHERE run_id=? AND sequence>? ORDER BY sequence LIMIT 500', (run_id, after))]

    def artifact_list(self, run_id):
        self.get('runs', run_id)
        with self.lock:
            return [json.loads(r[0]) for r in self.db.execute('SELECT doc FROM artifacts WHERE run_id=? ORDER BY rowid', (run_id,))]

    def put_checkpoint(self, db, checkpoint, state):
        """Append an immutable checkpoint and opaque state in the caller transaction."""
        db.execute('INSERT INTO checkpoints VALUES(?,?,?,?)',
                   (checkpoint['id'], checkpoint['run_id'], dumps(checkpoint), state))

    def checkpoint(self, ident):
        with self.lock:
            row = self.db.execute('SELECT doc FROM checkpoints WHERE id=?', (ident,)).fetchone()
        if not row:
            raise Problem('CHECKPOINT_NOT_FOUND', 'Checkpoint 不存在。', 404)
        return json.loads(row['doc'])

    def checkpoint_state(self, ident):
        with self.lock:
            row = self.db.execute('SELECT state FROM checkpoints WHERE id=?', (ident,)).fetchone()
        if not row:
            raise Problem('CHECKPOINT_NOT_FOUND', 'Checkpoint 不存在。', 404)
        return bytes(row['state'])

    def latest_checkpoint(self, run_id):
        self.get('runs', run_id)
        with self.lock:
            row = self.db.execute('SELECT doc FROM checkpoints WHERE run_id=? ORDER BY rowid DESC LIMIT 1', (run_id,)).fetchone()
        if not row:
            return None
        return json.loads(row['doc'])

    def put_control_evidence(self, db, evidence):
        db.execute('INSERT INTO control_evidence VALUES(?,?,?)',
                   (evidence['id'], evidence['run_id'], dumps(evidence)))

    def control_evidence(self, ident):
        with self.lock:
            row = self.db.execute('SELECT doc FROM control_evidence WHERE id=?', (ident,)).fetchone()
        if not row:
            raise Problem('EVIDENCE_NOT_FOUND', 'Replan Evidence 不存在。', 404)
        return json.loads(row['doc'])

    def put_gap(self, db, gap, failure_event_id):
        db.execute('INSERT INTO control_gaps VALUES(?,?,?,?) ON CONFLICT(run_id,failure_event_id) DO UPDATE SET doc=excluded.doc',
                   (gap['id'], gap['run_id'], failure_event_id, dumps(gap)))

    def gap_for_failure_event(self, run_id, failure_event_id):
        with self.lock:
            row = self.db.execute('SELECT doc FROM control_gaps WHERE run_id=? AND failure_event_id=?',
                                  (run_id, failure_event_id)).fetchone()
        return json.loads(row['doc']) if row else None

    def gaps_for_run(self, run_id):
        self.get('runs', run_id)
        with self.lock:
            rows = self.db.execute('SELECT doc FROM control_gaps WHERE run_id=? ORDER BY rowid', (run_id,)).fetchall()
        return [json.loads(row['doc']) for row in rows]

    def update_gap(self, db, gap):
        db.execute('UPDATE control_gaps SET doc=? WHERE id=?', (dumps(gap), gap['id']))

    def put_plan_revision(self, db, run_id, plan):
        db.execute('INSERT INTO plan_revisions VALUES(?,?,?)', (plan['id'], run_id, dumps(plan)))

    def plan_revision(self, ident):
        with self.lock:
            row = self.db.execute('SELECT doc FROM plan_revisions WHERE id=?', (ident,)).fetchone()
        if not row:
            raise Problem('PLAN_REVISION_NOT_FOUND', '计划版本不存在。', 404)
        return json.loads(row['doc'])

    def put_replan_attempt(self, db, attempt):
        db.execute('INSERT INTO replan_attempts VALUES(?,?,?) ON CONFLICT(id) DO UPDATE SET doc=excluded.doc',
                   (attempt['id'], attempt['origin_run_id'], dumps(attempt)))

    def replan_attempt(self, ident):
        with self.lock:
            row = self.db.execute('SELECT doc FROM replan_attempts WHERE id=?', (ident,)).fetchone()
        if not row:
            raise Problem('REPLAN_NOT_FOUND', 'ReplanAttempt 不存在。', 404)
        return json.loads(row['doc'])

    def replan_attempts(self, origin_run_id):
        self.get('runs', origin_run_id)
        with self.lock:
            rows = self.db.execute('SELECT doc FROM replan_attempts WHERE origin_run_id=? ORDER BY rowid DESC',
                                   (origin_run_id,)).fetchall()
        return [json.loads(row['doc']) for row in rows]

    def raw(self, resource_id):
        self.get('resources', resource_id)
        with self.lock:
            return self.db.execute('SELECT raw FROM resources WHERE id=?', (resource_id,)).fetchone()[0]

    def oauth_attempt(self, ident):
        with self.lock:
            row = self.db.execute('SELECT doc FROM oauth_attempts WHERE id=?', (ident,)).fetchone()
        if not row:
            raise Problem('AUTHORIZATION_STATE_INVALID', '授权状态无效。', 400)
        return json.loads(row['doc'])

    def oauth_attempt_by_state_digest(self, state_digest):
        with self.lock:
            rows = self.db.execute('SELECT doc FROM oauth_attempts').fetchall()
        for row in rows:
            attempt = json.loads(row['doc'])
            if hmac.compare_digest(attempt.get('state_digest', ''), state_digest):
                return attempt
        raise Problem('AUTHORIZATION_STATE_INVALID', '授权状态无效。', 400)

    def oauth_attempt_by_idempotency(self, idempotency_digest):
        with self.lock:
            rows = self.db.execute('SELECT doc FROM oauth_attempts').fetchall()
        for row in rows:
            attempt = json.loads(row['doc'])
            if hmac.compare_digest(attempt.get('idempotency_digest', ''), idempotency_digest):
                return attempt
        return None

    def put_oauth_attempt(self, db, attempt):
        db.execute('INSERT INTO oauth_attempts VALUES(?,?) ON CONFLICT(id) DO UPDATE SET doc=excluded.doc',
                   (attempt['id'], dumps(attempt)))

    def close(self):
        self.db.close()
