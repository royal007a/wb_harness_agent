import copy
import io
import json
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from jsonschema import Draft202012Validator

from adapters.pi_sidecar import PiSidecarClient
from backend.analysis import Problem
from backend.app import create_app
from backend.runtime_event_metadata import KINDS, fingerprint, project_runtime_event
from test_claude_research_runtime import PUBLIC_PDF, REQUEST, enabled_env


MARKER = 'PRIVATE_SENTINEL_76_正文'
ROOT = Path(__file__).resolve().parents[1]
SCHEMA = json.loads((ROOT / 'specs/v1/runtime-event-metadata.schema.json').read_text())
VALIDATOR = Draft202012Validator(SCHEMA)


@pytest.mark.parametrize('kind', sorted(KINDS))
def test_projection_recomputes_digest_never_copies_content(kind):
    payload = {'text': MARKER, 'structured_output': {'answer': MARKER},
               'tool_use_id': MARKER, 'errors': [MARKER], 'is_error': True,
               'usage': {MARKER: MARKER}, 'sha256': MARKER, 'unknown': MARKER}
    original = copy.deepcopy(payload)
    result = project_runtime_event(kind, payload)
    assert payload == original
    assert MARKER not in json.dumps(result, ensure_ascii=False)
    assert result['payload_sha256'] == fingerprint(payload)['sha256']
    assert result['payload_bytes'] == fingerprint(payload)['bytes']
    assert result['is_error'] is True
    VALIDATOR.validate(result)
    if kind == 'sdk.result':
        assert result['error_count'] == 1
        assert result['errors'] == [{'category': 'sdk_error', **fingerprint(MARKER)}]


def test_schema_and_projector_contracts_match_and_reject_raw_fields():
    assert set(SCHEMA['properties']['kind']['enum']) == KINDS
    result = project_runtime_event('sdk.result', {'errors': [MARKER] * 65, 'is_error': MARKER})
    assert result['error_count'] == 65 and len(result['errors']) == 64
    assert 'is_error' not in result
    VALIDATOR.validate(result)
    for field in ('text', 'structured_output', 'stderr', 'usage'):
        assert list(VALIDATOR.iter_errors({**result, field: MARKER}))
    assert list(VALIDATOR.iter_errors({**result, 'errors': [{'category': MARKER, **fingerprint('x')}]}))


@pytest.mark.parametrize('kind,payload', [
    (MARKER, {}), ([], {}), ('assistant.text', []),
    ('sdk.result', {'errors': MARKER}), ('assistant.text', {'x': float('nan')}),
])
def test_invalid_projection_is_fixed_error(kind, payload):
    with pytest.raises(Problem) as caught:
        project_runtime_event(kind, payload)
    assert caught.value.code == 'RUNTIME_EVENT_INVALID'
    assert MARKER not in str(caught.value)


def test_native_persists_only_metadata_but_publishes_original_child_text(tmp_path, monkeypatch):
    enabled_env(monkeypatch, tmp_path)

    async def stream(*args):
        for role in ('financial', 'industry', 'risk'):
            tool_id = MARKER + role
            yield {'kind': 'assistant.tool_use', 'agent_scope': 'parent', 'parent_tool_use_id': None,
                   'payload': {'tool_use_id': tool_id, 'tool': 'Agent', 'subagent_type': role}}
            yield {'kind': 'assistant.text', 'agent_scope': 'child', 'parent_tool_use_id': tool_id,
                   'payload': {'text': '未评估：' + MARKER, 'sha256': MARKER}}
            yield {'kind': 'assistant.tool_result', 'agent_scope': 'child', 'parent_tool_use_id': tool_id,
                   'payload': {'tool_use_id': tool_id, 'content': MARKER}}
        yield {'kind': 'sdk.result', 'agent_scope': 'parent', 'parent_tool_use_id': None,
               'payload': {'errors': [MARKER], 'structured_output': {'answer': MARKER}}}

    monkeypatch.setattr('backend.research_native.stream_native_research', stream)
    database = tmp_path / 'native.db'
    with TestClient(create_app(database, False), base_url='http://127.0.0.1') as client:
        resource = client.post('/api/local/research-native/documents?name=report.pdf', content=PUBLIC_PDF,
                               headers={'content-type': 'application/pdf'}).json()
        created = client.post('/api/local/research-native', json={**REQUEST, 'report_resource_id': resource['id']},
                              headers={'Idempotency-Key': 'privacy-native'})
        assert created.status_code == 202, created.text
        root = created.json()['initial_run']['id']
        service = client.app.state.service
        service.execute(root)
        detail = client.get('/api/local/research-native/' + root).json()
        assert detail['run']['status'] == 'succeeded'
        run_ids = [root] + [c['run']['id'] for c in detail['children']]
        saved = []
        for run_id in run_ids:
            events = client.get(f'/api/v1/runs/{run_id}/events').json()['items']
            assert MARKER not in json.dumps(events, ensure_ascii=False)
            saved.extend(events)
            for event in events:
                if event['event_type'].startswith('agent.sdk.'):
                    VALIDATOR.validate(event['data'])
        assert len([e for e in saved if e['event_type'] == 'agent.sdk.text']) == 3
        for child in detail['children']:
            artifact = service.store.artifact_list(child['run']['id'])[0]
            response = client.get(f"/api/v1/artifacts/{artifact['id']}/content")
            assert '未评估：' + MARKER in response.text
        # Existing data is not silently rewritten by the new projection or restart.
        with service.store.transaction() as db:
            service.store.event(db, service.store.get('runs', root), 'agent.sdk.text', {'text': 'legacy-body'})
        snapshot = {run_id: service.store.events(run_id) for run_id in run_ids}
    with TestClient(create_app(database, False), base_url='http://127.0.0.1') as client:
        for run_id in run_ids:
            assert client.app.state.service.store.events(run_id) == snapshot[run_id]


def test_pi_real_adapter_extracts_candidate_from_memory_not_persisted_event(tmp_path, monkeypatch):
    class SyntheticSidecar:
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def health(self): return {'runtime_enabled': False, 'external_calls': 0}
        def start(self, **kwargs): self.resource = kwargs['resource_ref']
        def drain_until_done(self, run_id):
            finding = {'status': 'needs_human', 'risk_level': 'high',
                       'evidence_refs': [f'evidence://{self.resource}/clause-12.3/page-8'],
                       'recommendation': MARKER}
            return [{'platform_type': 'tool.call.completed', 'payload': {'result': MARKER}},
                    {'platform_type': 'run.result.proposed', 'payload': {
                        'unknown': MARKER, 'messages': [{'role': 'assistant', 'content': [
                            {'type': 'text', 'text': json.dumps(finding, ensure_ascii=False)}]}]}}]

    monkeypatch.setattr('adapters.pi_contract_review.PiSidecarClient', SyntheticSidecar)
    with TestClient(create_app(tmp_path / 'pi.db', False), base_url='http://127.0.0.1') as client:
        resource = client.post('/api/local/research-native/documents?name=contract.pdf', content=PUBLIC_PDF,
                               headers={'content-type': 'application/pdf'}).json()
        response = client.post('/api/local/pi-contract-review', json={
            'resource_id': resource['id'], 'objective': '审查合同', 'timeout_seconds': 30,
        }, headers={'Idempotency-Key': 'privacy-pi'})
        assert response.status_code == 202, response.text
        run_id = response.json()['initial_run']['id']
        client.app.state.service.execute(run_id)
        detail = client.get('/api/local/pi-contract-review/' + run_id).json()
        assert detail['run']['status'] == 'waiting_approval'
        events = client.get(f'/api/local/pi-contract-review/{run_id}/events').json()['events']
        assert MARKER not in json.dumps(events, ensure_ascii=False)
        projected = [e['data']['payload'] for e in events if e['event_type'].startswith('pi.')]
        assert len(projected) == 2
        for payload in projected: VALIDATOR.validate(payload)
        artifact = next(a for a in detail['artifacts'] if a['name'] == 'pi-contract-review.json')
        assert client.get(f"/api/v1/artifacts/{artifact['id']}/content").json()['recommendation'] == MARKER


def test_pi_stderr_not_read_or_propagated(monkeypatch):
    def spawn(*args, **kwargs):
        assert kwargs['stderr'] == subprocess.DEVNULL
        return SimpleNamespace(stdout=io.StringIO(''), stderr=SimpleNamespace(read=lambda: pytest.fail('stderr read')))
    monkeypatch.setattr(subprocess, 'Popen', spawn)
    client = PiSidecarClient()
    client.start_process()
    with pytest.raises(RuntimeError, match='^PI_SIDECAR_EOF$'):
        client._read()


def test_invalid_pi_event_fails_without_persisting_unknown_kind(tmp_path, monkeypatch):
    def start(_self, request, emit, check):
        emit(MARKER, {'text': MARKER})
        pytest.fail('unknown observation must fail before candidate publication')
    monkeypatch.setattr('adapters.pi_contract_review.PiContractReviewAdapter.start_run', start)
    with TestClient(create_app(tmp_path / 'invalid-pi.db', False), base_url='http://127.0.0.1') as client:
        resource = client.post('/api/local/research-native/documents?name=contract.pdf', content=PUBLIC_PDF,
                               headers={'content-type': 'application/pdf'}).json()
        response = client.post('/api/local/pi-contract-review', json={
            'resource_id': resource['id'], 'objective': '审查合同', 'timeout_seconds': 30,
        }, headers={'Idempotency-Key': 'invalid-pi'})
        assert response.status_code == 202
        run_id = response.json()['initial_run']['id']
        service = client.app.state.service
        service.execute(run_id)
        run = service.store.get('runs', run_id)
        assert run['status'] == 'failed' and run['exit_reason'] == 'RUNTIME_EVENT_INVALID'
        assert not service.store.artifact_list(run_id)
        events = service.store.events(run_id)
        assert not any(e['event_type'].startswith('pi.') for e in events)
        assert MARKER not in json.dumps(events, ensure_ascii=False)


@pytest.mark.parametrize('operation', ['health', 'start', 'drain', 'stream', 'cancel'])
def test_untrusted_sidecar_error_code_is_not_a_diagnostic_channel(monkeypatch, operation):
    client = PiSidecarClient()
    monkeypatch.setattr(client, 'start_process', lambda: None)
    monkeypatch.setattr(client, '_send', lambda payload: None)
    monkeypatch.setattr(client, '_read', lambda: {'op': 'error', 'run_id': 'run_test', 'code': MARKER})
    calls = {'health': lambda: client.health(), 'start': lambda: client.start(run_id='run_test', resource_ref='res_test'),
             'drain': lambda: client.drain_until_done('run_test'), 'stream': lambda: client.stream(run_id='run_test'),
             'cancel': lambda: client.cancel(run_id='run_test')}
    with pytest.raises(RuntimeError, match='^PI_SIDECAR_ERROR$'):
        calls[operation]()
