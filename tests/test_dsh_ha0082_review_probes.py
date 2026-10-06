import contextlib
import json
import sqlite3

import httpx
import pytest

from test_dsh_payment_findings import client, submit, reply, run_script, findings


def script(n, results):
    if n == 1:
        return reply(calls=[('search_document', {'query': '付款'}), ('search_document', {'query': '付款', 'offset': 3})])
    if n == 2:
        return reply(calls=[('submit_findings', findings())])
    if n == 3:
        return reply(calls=[('submit_findings', findings('验收合格后300天内付款'))])
    return reply('完成')


def statuses(detail):
    return {s['step_id']: s['status'] for s in detail['plan']['steps']}


def test_rejection_and_plan_atomic_on_db_failure(client, monkeypatch):
    ident = submit(client)
    rt = client.app.state.service.dsh
    original = rt.store.event
    def event(db, run, kind, data=None):
        if kind == 'dsh.plan.step' and any(s['step_id'] == 'S3' and s['status'] == 'blocked' for s in data['steps']):
            raise sqlite3.OperationalError('synthetic failure')
        return original(db, run, kind, data)
    monkeypatch.setattr(rt.store, 'event', event)
    _, detail, _ = run_script(client, ident, script)
    checks = [e['data'] for e in rt.store.events(ident) if e['event_type'] == 'dsh.findings.checked']
    assert detail['run']['status'] == 'failed' and detail['artifacts'] == []
    expected = 'done' if checks[-1]['accepted'] else 'blocked'
    assert statuses(detail)['S3'] == expected, (statuses(detail), checks)


def test_cancel_between_rejection_and_projection(client, monkeypatch):
    ident = submit(client)
    rt = client.app.state.service.dsh
    original_event, original_tx = rt.store.event, rt.store.transaction
    pending = []
    def event(db, run, kind, data=None):
        result = original_event(db, run, kind, data)
        if kind == 'dsh.findings.checked' and data['submission_number'] == 2:
            pending.append(True)
        return result
    @contextlib.contextmanager
    def transaction():
        with original_tx() as db:
            yield db
        if pending:
            pending.clear()
            rt.cancel(ident)
    monkeypatch.setattr(rt.store, 'event', event)
    monkeypatch.setattr(rt.store, 'transaction', transaction)
    _, detail, _ = run_script(client, ident, script)
    assert detail['run']['status'] == 'cancelled' and detail['artifacts'] == []
    assert statuses(detail)['S3'] == 'blocked', statuses(detail)


def test_accepted_projection_not_committed_without_audit(client, monkeypatch):
    ident = submit(client)
    rt = client.app.state.service.dsh
    original = rt.store.event
    def event(db, run, kind, data=None):
        if kind == 'dsh.findings.checked' and data['accepted']:
            raise sqlite3.OperationalError('synthetic failure')
        return original(db, run, kind, data)
    monkeypatch.setattr(rt.store, 'event', event)
    _, detail, _ = run_script(client, ident, script)
    assert detail['run']['status'] == 'failed' and detail['artifacts'] == []
    assert not [e for e in rt.store.events(ident) if e['event_type'] == 'dsh.findings.checked']
    assert statuses(detail)['S3'] != 'done', statuses(detail)


def test_evidence_ids_match_completed_plan(client):
    ident = submit(client)
    _, detail, _ = run_script(client, ident, lambda n, r: script(n, r) if n < 3 else reply('完成'))
    assert detail['run']['status'] == 'succeeded', detail['run']
    step = detail['plan']['steps'][0]
    assert step['status'] == 'done' and step['missing_ids'] == []
    assert step['evidence_ids'] == ['clause-1', 'clause-2', 'clause-3', 'clause-4'], step


def test_httpx_timeout_has_explicit_category(client):
    ident = submit(client)
    rt = client.app.state.service.dsh
    async def provider(payload, limit):
        raise httpx.ReadTimeout('SYNTH_PRIVATE_ERROR')
    rt.send_probe = provider
    rt.execute(ident)
    detail = rt.detail(ident)
    assert detail['budget']['reserved'] > 0 and detail['budget']['status'] == 'usage_unknown'
    assert detail['run']['exit_reason'] == 'DSH_PROVIDER_TIMEOUT', detail['run']['exit_reason']


def test_publication_failure_rolls_back_artifacts_and_success(client, monkeypatch):
    ident = submit(client)
    rt = client.app.state.service.dsh
    original = rt.store.event
    def event(db, run, kind, data=None):
        if kind == 'run.succeeded':
            raise sqlite3.OperationalError('synthetic publication failure')
        return original(db, run, kind, data)
    monkeypatch.setattr(rt.store, 'event', event)
    _, detail, _ = run_script(client, ident, lambda n, r: script(n, r) if n < 3 else reply('完成'))
    assert detail['run']['status'] == 'failed' and detail['artifacts'] == []
    assert not [e for e in rt.store.events(ident) if e['event_type'] == 'run.succeeded']
    assert statuses(detail)['S4'] == 'ready'


def test_delayed_cleanup_stops_with_service(client, monkeypatch):
    import threading
    import backend.dsh_runtime as module
    rt = client.app.state.service.dsh
    called = threading.Event()
    def cleanup(root, wait_seconds=0):
        called.set()
        return {'cleaned': 0, 'pending': 0, 'retained': 0}
    monkeypatch.setattr(module, 'cleanup_workspaces', cleanup)
    rt.cleanup_status = {'cleaned': 0, 'pending': 1, 'retained': 0, 'retries': 0}
    rt.cleanup_retry_seconds = 0.1
    rt._schedule_cleanup(1)
    rt.service.stop()
    assert not called.wait(0.5), 'cleanup callback still ran after Service.stop()'


def test_cancel_before_publication_no_artifacts(client, monkeypatch):
    ident = submit(client)
    rt = client.app.state.service.dsh
    original = rt.adapter.run
    def adapter(*a, **kw):
        result = original(*a, **kw)
        rt.cancel(ident)
        return result
    monkeypatch.setattr(rt.adapter, 'run', adapter)
    _, detail, _ = run_script(client, ident, lambda n, r: script(n, r) if n < 3 else reply('完成'))
    assert detail['run']['status'] == 'cancelled' and detail['artifacts'] == []
    assert sum(e['event_type'] in {'run.succeeded', 'run.cancelled', 'run.failed'} for e in rt.store.events(ident)) == 1


def test_cancel_after_publication_does_not_override(client):
    ident = submit(client)
    rt, detail, _ = run_script(client, ident, lambda n, r: script(n, r) if n < 3 else reply('完成'))
    before = rt.store.db.total_changes
    rt.cancel(ident)
    assert rt.detail(ident) == detail
    assert rt.store.db.total_changes == before


def test_prior_findings_contract_compatibility(client):
    import subprocess
    from jsonschema import Draft202012Validator
    from backend.dsh_runtime import SCHEMA
    ident = submit(client)
    rt, detail, _ = run_script(client, ident, lambda n, r: script(n, r) if n < 3 else reply('完成'))
    art = next(a for a in detail['artifacts'] if a['name'] == 'dsh-findings.json')
    record = json.loads(rt.store.db.execute('SELECT body FROM artifacts WHERE id=?', (art['id'],)).fetchone()[0])
    record.pop('submissions')
    old = json.loads(subprocess.check_output(['git', 'show', '29e1966:specs/v1/dsh-runtime.schema.json']))
    def validator(schema):
        return Draft202012Validator({'$ref': '#/$defs/findings', '$defs': schema['$defs']})
    assert validator(old).is_valid(record)
    assert validator(SCHEMA).is_valid(record), [e.message for e in validator(SCHEMA).iter_errors(record)]
