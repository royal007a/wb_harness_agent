"""Independent review probes, not part of the author's claimed suite."""
import json
import pytest

import backend.dsh_runtime as runtime
from test_dsh_payment_findings import client, submit, reply, run_script  # noqa: F401


@pytest.mark.parametrize('failure', ['scanner', 'scan_event'])
def test_scan_failure_rolls_back_publication(client, monkeypatch, failure):
    ident = submit(client, template='free', document='第1条 付款\n验收后30天付款。')
    rt = client.app.state.service.dsh
    if failure == 'scanner':
        def fail_scan(text):
            raise RuntimeError('SYNTH_REVIEW_PRIVATE_98')
        monkeypatch.setattr(runtime, 'scan_output', fail_scan)
    else:
        original = rt.store.event
        def fail_event(db, run, kind, payload, *args, **kwargs):
            if kind == 'dsh.output.scanned':
                raise RuntimeError('SYNTH_REVIEW_PRIVATE_98')
            return original(db, run, kind, payload, *args, **kwargs)
        monkeypatch.setattr(rt.store, 'event', fail_event)
    rt, detail, calls = run_script(client, ident, lambda n, results:
        reply(calls=[('read_clause', {'clause_id': 'clause-1'})]) if n == 1
        else reply('clause-1：验收后30天付款。'))
    assert len(calls) == 2
    assert detail['run']['status'] == 'failed'
    assert detail['artifacts'] == []
    events = rt.store.events(ident)
    assert not [e for e in events if e['event_type'] in ('dsh.output.scanned', 'run.succeeded')]
    assert events[-1]['event_type'] == 'run.failed'
    assert 'SYNTH_REVIEW_PRIVATE_98' not in json.dumps(events)
