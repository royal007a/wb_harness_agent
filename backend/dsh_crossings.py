"""Run-local crossing replay; durable metadata is NOT a resumable response cache."""
from __future__ import annotations

import copy
import hashlib
import json
import threading
import uuid

from .analysis import Problem


def fingerprint(value):
    try:
        data = json.dumps(value, sort_keys=True, ensure_ascii=True,
                          separators=(',', ':'), allow_nan=False).encode()
    except (TypeError, ValueError, RecursionError):
        raise Problem('DSH_CROSSING_INVALID', '调用信封无效。', 409) from None
    return hashlib.sha256(data).hexdigest()


def initialize(store):
    with store.transaction() as db:
        db.execute('''CREATE TABLE IF NOT EXISTS dsh_crossings (
            run_id TEXT NOT NULL, generation TEXT NOT NULL, crossing_id TEXT NOT NULL,
            kind TEXT NOT NULL, model_round INTEGER NOT NULL, tool_ordinal INTEGER NOT NULL,
            request_sha256 TEXT, response_sha256 TEXT, origin_id_sha256 TEXT,
            status TEXT NOT NULL,
            PRIMARY KEY(run_id, generation, crossing_id))''')


def retire(store, db, run_id, generation=None):
    """No resend after restart/termination, even if the action committed before its receipt."""
    query = "SELECT * FROM dsh_crossings WHERE run_id=? AND status IN ('issued','in_flight')"
    args = (run_id,)
    if generation is not None:
        query += ' AND generation=?'
        args += (generation,)
    rows = db.execute(query, args).fetchall()
    run = store.get('runs', run_id)
    for row in rows:
        status = 'unknown' if row['status'] == 'in_flight' else 'failed'
        db.execute('UPDATE dsh_crossings SET status=? WHERE run_id=? AND generation=? AND crossing_id=?',
                   (status, run_id, row['generation'], row['crossing_id']))
        store.event(db, run, 'dsh.crossing', {
            'generation': row['generation'], 'crossing_id': row['crossing_id'],
            'kind': row['kind'], 'model_round': row['model_round'],
            'tool_ordinal': row['tool_ordinal'], 'status': status,
            'request_sha256': row['request_sha256'], 'response_sha256': row['response_sha256']})


class Crossings:
    def __init__(self, store, run_id, check):
        self.store, self.run_id, self.check = store, run_id, check
        self.generation = uuid.uuid4().hex
        self.lock = threading.RLock()  # Never hold the database lock during a Provider call.
        self.entries, self.responses = {}, {}
        first = self._entry('m_1', 'model', 1)
        with store.transaction() as db:
            check()
            self._insert(db, first)
        self.entries[first['crossing_id']] = first

    def _entry(self, ident, kind, turn, ordinal=0, request=None, origin=None):
        return dict(crossing_id=ident, kind=kind, model_round=turn, tool_ordinal=ordinal,
                    request_sha256=fingerprint(request) if request is not None else None,
                    response_sha256=None, origin_id_sha256=fingerprint(origin) if origin is not None else None,
                    status='issued')

    def _event(self, db, item):
        self.store.event(db, self.store.get('runs', self.run_id), 'dsh.crossing',
                         dict(generation=self.generation, **item))

    def _insert(self, db, item):
        db.execute('''INSERT INTO dsh_crossings
            (run_id,generation,crossing_id,kind,model_round,tool_ordinal,request_sha256,
             response_sha256,origin_id_sha256,status) VALUES (?,?,?,?,?,?,?,?,?,?)''',
            (self.run_id, self.generation, *[item[k] for k in (
                'crossing_id', 'kind', 'model_round', 'tool_ordinal', 'request_sha256',
                'response_sha256', 'origin_id_sha256', 'status')]))
        self._event(db, item)

    def _update(self, db, item):
        db.execute('''UPDATE dsh_crossings SET status=?,request_sha256=?,response_sha256=?
            WHERE run_id=? AND generation=? AND crossing_id=?''',
            (item['status'], item['request_sha256'], item['response_sha256'],
             self.run_id, self.generation, item['crossing_id']))
        self._event(db, item)

    def invoke(self, kind, envelope, callback):
        with self.lock:
            self.check()  # Includes cancellation/deadline, also before serving a cached receipt.
            if (not isinstance(envelope, dict) or set(envelope) != {'crossing_id', 'request'}
                    or not isinstance(envelope['crossing_id'], str)
                    or not isinstance(envelope['request'], dict)):
                raise Problem('DSH_CROSSING_INVALID', '调用信封无效。', 409)
            ident, request = envelope['crossing_id'], copy.deepcopy(envelope['request'])
            item = self.entries.get(ident)
            if item is None or item['kind'] != kind:
                raise Problem('DSH_CROSSING_NOT_ISSUED', '调用身份未由本次运行签发。', 409)
            sha = fingerprint(request)
            if item['request_sha256'] is not None and sha != item['request_sha256']:
                raise Problem('DSH_CROSSING_CONFLICT', '同一调用身份的内容不一致。', 409)
            if item['status'] == 'completed' and ident in self.responses:
                return copy.deepcopy(self.responses[ident])
            if item['status'] != 'issued':
                raise Problem('DSH_CROSSING_UNAVAILABLE', '调用结果不可重放，不会重新执行。', 409)
            if kind == 'model' and any(e['kind'] == 'tool' and e['model_round'] == item['model_round'] - 1
                                       and e['status'] != 'completed' for e in self.entries.values()):
                raise Problem('DSH_CROSSING_PREDECESSOR_PENDING', '上一轮工具尚未完成。', 409)
            active = dict(item, request_sha256=sha, status='in_flight')
            with self.store.transaction() as db:
                self.check()
                self._update(db, active)
            self.entries[ident] = active
            try:
                value = copy.deepcopy(callback(request))
                issued = []
                if kind == 'model':
                    turn = item['model_round']
                    # The Provider's raw ID can repeat next round; never use it as identity.
                    for ordinal, call in enumerate(value['tool_calls'], 1):
                        ticket = 't_' + str(turn) + '_' + str(ordinal) + '_' + uuid.uuid4().hex
                        issued.append(self._entry(ticket, 'tool', turn, ordinal,
                            {'name': call['name'], 'arguments': json.loads(call['arguments'])}, call['id']))
                        call['id'] = ticket
                    next_id = f'm_{turn + 1}'
                    issued.append(self._entry(next_id, 'model', turn + 1))
                    value = {'value': value, 'next_model_crossing': next_id}
                completed = dict(active, status='completed', response_sha256=fingerprint(value))
                with self.store.transaction() as db:
                    self.check()
                    self._update(db, completed)
                    for entry in issued:
                        self._insert(db, entry)
                self.entries[ident] = completed
                self.entries.update({entry['crossing_id']: entry for entry in issued})
                self.responses[ident] = copy.deepcopy(value)
                return value
            except BaseException:
                # The action may already have committed or reached the Provider. Do not retry.
                unknown = dict(active, status='unknown')
                try:
                    with self.store.transaction() as db:
                        self._update(db, unknown)
                    self.entries[ident] = unknown
                except Exception:
                    pass  # Durable in_flight is converted to unknown by recovery.
                raise
