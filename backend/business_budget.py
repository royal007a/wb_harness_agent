"""Internal budget boundary, not a public API or an enabled business runtime.

Only the trusted platform may create roots, bind members, supply token counters
or transports, and recover abandoned calls after acquiring its execution lease.
Construction is explicit: existing Service startup does not create these tables.
"""
from __future__ import annotations

import asyncio
import copy
from dataclasses import dataclass
from hashlib import sha256
import json
import math
import re

from .analysis import Problem


MAX_TOKENS = 20_000_000
PURPOSES = frozenset({'primary', 'child', 'retry', 'compaction', 'guard'})


def error(code):
    return Problem(code, '业务模型调用未通过预算或状态检查。', 409)


def integer(value, *, minimum=0):
    if type(value) is not int or not minimum <= value <= MAX_TOKENS:
        raise error('BUSINESS_BUDGET_INVALID_NUMBER')
    return value


def identifier(value):
    if not isinstance(value, str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,128}', value):
        raise error('BUSINESS_BUDGET_INVALID_ID')
    return value


def digest_value(value):
    if not isinstance(value, str) or not re.fullmatch(r'[a-f0-9]{64}', value):
        raise error('BUSINESS_BUDGET_INVALID_DIGEST')
    return value


class BusinessTokenLedger:
    def __init__(self, store):
        self.store = store
        with store.transaction() as db:
            db.execute('''CREATE TABLE IF NOT EXISTS business_budget_roots(
                id TEXT PRIMARY KEY, binding_digest TEXT NOT NULL,
                token_limit INTEGER NOT NULL, status TEXT NOT NULL)''')
            db.execute('''CREATE TABLE IF NOT EXISTS business_budget_members(
                id TEXT PRIMARY KEY, root_id TEXT NOT NULL REFERENCES business_budget_roots(id),
                parent_id TEXT REFERENCES business_budget_members(id))''')
            db.execute('''CREATE TABLE IF NOT EXISTS business_budget_calls(
                root_id TEXT NOT NULL REFERENCES business_budget_roots(id),
                call_id TEXT NOT NULL, member_id TEXT NOT NULL REFERENCES business_budget_members(id),
                request_digest TEXT NOT NULL, purpose TEXT NOT NULL,
                input_bound INTEGER NOT NULL, output_limit INTEGER NOT NULL,
                status TEXT NOT NULL, input_tokens INTEGER, output_tokens INTEGER,
                PRIMARY KEY(root_id, call_id))''')

    @staticmethod
    def _root(db, root_id):
        row = db.execute('SELECT * FROM business_budget_roots WHERE id=?', (root_id,)).fetchone()
        if row is None:
            raise error('BUSINESS_BUDGET_ROOT_MISSING')
        return row

    @classmethod
    def _member_root(cls, db, member_id):
        member = db.execute('SELECT * FROM business_budget_members WHERE id=?', (member_id,)).fetchone()
        if member is None:
            raise error('BUSINESS_BUDGET_MEMBER_MISSING')
        return cls._root(db, member['root_id'])

    @staticmethod
    def _active(root):
        if root['status'] != 'active':
            raise error('BUSINESS_BUDGET_STOPPED')

    @classmethod
    def _snapshot(cls, db, root_id):
        root = cls._root(db, root_id)
        sums = db.execute('''SELECT
            COALESCE(SUM(CASE WHEN status IN ('settled','breached')
                THEN input_tokens + output_tokens ELSE 0 END),0) AS spent,
            COALESCE(SUM(CASE WHEN status IN ('reserved','sent','unknown')
                THEN input_bound + output_limit ELSE 0 END),0) AS reserved,
            COUNT(*) AS calls FROM business_budget_calls WHERE root_id=?''', (root_id,)).fetchone()
        return {**dict(root), **dict(sums),
                'remaining': max(0, root['token_limit'] - sums['spent'] - sums['reserved'])}

    def snapshot(self, root_id):
        with self.store.lock:
            return self._snapshot(self.store.db, root_id)

    def register_root(self, root_id, binding_digest, token_limit=MAX_TOKENS):
        identifier(root_id)
        digest_value(binding_digest)
        integer(token_limit, minimum=1)
        with self.store.transaction() as db:
            if db.execute('SELECT 1 FROM business_budget_members WHERE id=?', (root_id,)).fetchone():
                raise error('BUSINESS_BUDGET_ALREADY_REGISTERED')
            db.execute('INSERT INTO business_budget_roots VALUES(?,?,?,?)',
                       (root_id, binding_digest, token_limit, 'active'))
            db.execute('INSERT INTO business_budget_members VALUES(?,?,NULL)', (root_id, root_id))

    def bind_member(self, member_id, parent_id):
        identifier(member_id)
        identifier(parent_id)
        with self.store.transaction() as db:
            root = self._member_root(db, parent_id)
            self._active(root)
            if db.execute('SELECT 1 FROM business_budget_members WHERE id=?', (member_id,)).fetchone():
                raise error('BUSINESS_BUDGET_ALREADY_REGISTERED')
            db.execute('INSERT INTO business_budget_members VALUES(?,?,?)', (member_id, root['id'], parent_id))

    def reserve(self, member_id, call_id, *, binding_digest, request_digest,
                input_bound, output_limit, purpose='primary'):
        identifier(member_id)
        identifier(call_id)
        digest_value(binding_digest)
        digest_value(request_digest)
        integer(input_bound, minimum=1)
        integer(output_limit, minimum=1)
        if not isinstance(purpose, str) or purpose not in PURPOSES:
            raise error('BUSINESS_BUDGET_INVALID_PURPOSE')
        with self.store.transaction() as db:
            root = self._member_root(db, member_id)
            self._active(root)
            if root['binding_digest'] != binding_digest:
                raise error('BUSINESS_BUDGET_BINDING_MISMATCH')
            if db.execute('SELECT 1 FROM business_budget_calls WHERE root_id=? AND call_id=?',
                          (root['id'], call_id)).fetchone():
                raise error('BUSINESS_MODEL_CALL_ALREADY_USED')
            if self._snapshot(db, root['id'])['remaining'] < input_bound + output_limit:
                raise error('BUSINESS_TOKEN_BUDGET_EXHAUSTED')
            db.execute('''INSERT INTO business_budget_calls
                (root_id,call_id,member_id,request_digest,purpose,input_bound,output_limit,status)
                VALUES(?,?,?,?,?,?,?,'reserved')''',
                (root['id'], call_id, member_id, request_digest, purpose, input_bound, output_limit))
            return root['id']

    @staticmethod
    def _call(db, root_id, call_id):
        row = db.execute('SELECT * FROM business_budget_calls WHERE root_id=? AND call_id=?',
                         (root_id, call_id)).fetchone()
        if row is None:
            raise error('BUSINESS_MODEL_CALL_MISSING')
        return row

    def mark_sent(self, root_id, call_id):
        with self.store.transaction() as db:
            self._active(self._root(db, root_id))
            if self._call(db, root_id, call_id)['status'] != 'reserved':
                raise error('BUSINESS_MODEL_CALL_STATE')
            db.execute("UPDATE business_budget_calls SET status='sent' WHERE root_id=? AND call_id=?",
                       (root_id, call_id))

    def abandon(self, root_id, call_id):
        """Unsent is releasable; possibly sent is never refunded as zero usage."""
        with self.store.transaction() as db:
            state = self._call(db, root_id, call_id)['status']
            if state not in {'reserved', 'sent'}:
                return
            db.execute('UPDATE business_budget_calls SET status=? WHERE root_id=? AND call_id=?',
                       ('released' if state == 'reserved' else 'unknown', root_id, call_id))
            if state == 'sent':
                db.execute("UPDATE business_budget_roots SET status='usage_unknown' WHERE id=? AND status='active'",
                           (root_id,))

    def settle(self, root_id, call_id, usage):
        failure = None
        with self.store.transaction() as db:
            call = self._call(db, root_id, call_id)
            if call['status'] != 'sent':
                raise error('BUSINESS_MODEL_CALL_STATE')
            valid = (isinstance(usage, dict) and
                     all(type(usage.get(k)) is int and 0 <= usage[k] <= 2 * MAX_TOKENS
                         for k in ('input_tokens', 'output_tokens', 'total_tokens')) and
                     usage['total_tokens'] == usage['input_tokens'] + usage['output_tokens'])
            if not valid:
                db.execute("UPDATE business_budget_calls SET status='unknown' WHERE root_id=? AND call_id=?",
                           (root_id, call_id))
                failure = 'BUSINESS_MODEL_USAGE_INVALID'
                root_status = 'usage_unknown'
            else:
                breach = usage['input_tokens'] > call['input_bound'] or usage['output_tokens'] > call['output_limit']
                db.execute('''UPDATE business_budget_calls SET status=?,input_tokens=?,output_tokens=?
                    WHERE root_id=? AND call_id=?''',
                    ('breached' if breach else 'settled', usage['input_tokens'], usage['output_tokens'], root_id, call_id))
                if breach:
                    failure, root_status = 'BUSINESS_MODEL_USAGE_BREACH', 'breached'
            if failure:
                db.execute('UPDATE business_budget_roots SET status=? WHERE id=? AND status=\'active\'',
                           (root_status, root_id))
        # Raise after committing the fail-closed state, not inside the transaction.
        if failure:
            raise error(failure)

    def cancel(self, root_id):
        with self.store.transaction() as db:
            self._root(db, root_id)
            db.execute("UPDATE business_budget_roots SET status='cancelled' WHERE id=? AND status='active'", (root_id,))

    def require_active(self, root_id):
        with self.store.lock:
            self._active(self._root(self.store.db, root_id))

    def recover(self, root_id):
        """Exclusive owner only, after all old senders have terminated."""
        with self.store.transaction() as db:
            self._root(db, root_id)
            db.execute("UPDATE business_budget_calls SET status='released' WHERE root_id=? AND status='reserved'", (root_id,))
            sent = db.execute("UPDATE business_budget_calls SET status='unknown' WHERE root_id=? AND status='sent'", (root_id,)).rowcount
            if sent:
                db.execute("UPDATE business_budget_roots SET status='usage_unknown' WHERE id=? AND status='active'", (root_id,))


@dataclass(frozen=True)
class ModelCallResult:
    value: object
    usage: dict | None


async def budgeted_model_call(ledger, *, member_id, call_id, binding_digest, payload,
                              input_counter, output_limit, send, timeout_seconds,
                              purpose='primary', cancel_event=None):
    """Call one trusted transport once; no retries, tools, credentials or HTTP here.

    input_counter must establish a provider-specific safe input upper bound.
    send must enforce output_limit and disable hidden retries. Both obligations
    need independent validation before wiring this boundary to a real provider.
    """
    if (type(timeout_seconds) not in (int, float) or not math.isfinite(timeout_seconds)
            or not 0 < timeout_seconds <= 3600):
        raise error('BUSINESS_MODEL_INVALID_TIMEOUT')
    integer(output_limit, minimum=1)
    frozen = copy.deepcopy(payload)
    encoded = json.dumps(frozen, ensure_ascii=False, allow_nan=False, sort_keys=True).encode()
    if len(encoded) > 256 * 1024:
        raise error('BUSINESS_MODEL_INPUT_LIMIT')
    input_bound = integer(input_counter(copy.deepcopy(frozen)), minimum=1)
    if cancel_event is not None and cancel_event.is_set():
        raise asyncio.CancelledError()
    request_digest = sha256(encoded + b'\0' + str(output_limit).encode()).hexdigest()
    root_id = ledger.reserve(member_id, call_id, binding_digest=binding_digest,
                             request_digest=request_digest, input_bound=input_bound,
                             output_limit=output_limit, purpose=purpose)
    sender = watcher = None
    try:
        if cancel_event is not None and cancel_event.is_set():
            raise asyncio.CancelledError()
        ledger.mark_sent(root_id, call_id)
        async def dispatch():
            ledger.require_active(root_id)
            if cancel_event is not None and cancel_event.is_set():
                raise asyncio.CancelledError()
            return await send(frozen, output_limit)
        sender = asyncio.create_task(dispatch())
        waiting = {sender}
        if cancel_event is not None:
            watcher = asyncio.create_task(cancel_event.wait())
            waiting.add(watcher)
        await asyncio.wait(waiting, timeout=timeout_seconds, return_when=asyncio.FIRST_COMPLETED)
        if cancel_event is not None and cancel_event.is_set():
            raise asyncio.CancelledError()
        if not sender.done():
            raise TimeoutError()
        result = sender.result()
        if not isinstance(result, ModelCallResult):
            ledger.settle(root_id, call_id, None)
        ledger.settle(root_id, call_id, result.usage)
        ledger.require_active(root_id)
        if cancel_event is not None and cancel_event.is_set():
            raise asyncio.CancelledError()
        return result.value
    except BaseException:
        ledger.abandon(root_id, call_id)
        raise
    finally:
        for task in (sender, watcher):
            if task is not None and not task.done():
                task.cancel()
        tasks = [t for t in (sender, watcher) if t is not None]
        if tasks:
            # An uncooperative transport must not hold the caller forever. Its
            # reservation remains uncertain/frozen; late output is never settled.
            await asyncio.wait(tasks, timeout=0.1)
            def consume(task):
                if not task.cancelled():
                    task.exception()
            for task in tasks:
                task.add_done_callback(consume)
