from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.app import create_app


PI_ROOT = Path(__file__).parents[1] / 'pi-adapter'


@pytest.fixture
def app(tmp_path):
    return create_app(tmp_path / 'pi-runtime.db', run_worker=False)


@pytest.fixture
def client(app):
    with TestClient(app, base_url='http://127.0.0.1') as test_client:
        yield test_client


@pytest.mark.skipif(not (PI_ROOT / 'node_modules').is_dir(), reason='run npm ci in pi-adapter first')
def test_pi_product_run_persists_artifact_evidence_and_requires_gate(client, app):
    uploaded = client.post(
        '/api/local/research-native/documents?name=contract-fixture.pdf',
        content=b'%PDF-1.7\nfixture',
        headers={'content-type': 'application/pdf'},
    )
    assert uploaded.status_code == 201, uploaded.text
    resource = uploaded.json()
    created = client.post(
        '/api/local/pi-contract-review',
        json={'resource_id': resource['id'], 'objective': '审查价格调整条款', 'timeout_seconds': 30},
        headers={'Idempotency-Key': 'pi-runtime-create-1'},
    )
    assert created.status_code == 202, created.text
    run_id = created.json()['initial_run']['id']

    app.state.service.execute(run_id)
    detail = client.get('/api/local/pi-contract-review/' + run_id).json()
    assert detail['run']['status'] == 'waiting_approval'
    assert detail['gate_required'] is True
    assert detail['runtime_enabled'] is False and detail['external_calls'] == 0
    assert {item['name'] for item in detail['artifacts']} == {
        'pi-contract-review.json', 'pi-contract-review-handoff.json'
    }
    events = app.state.service.store.events(run_id)
    proposed = [event for event in events if event['event_type'] == 'evidence.proposed']
    assert proposed and proposed[-1]['data']['evidence_refs'] == [
        f"evidence://{resource['id']}/clause-12.3/page-8"
    ]
    assert not any(event['event_type'] == 'run.succeeded' for event in events)

    gate = client.post(
        f'/api/local/pi-contract-review/{run_id}:gate',
        json={'decision': 'pass', 'reason': '人工核对引用与风险建议'},
        headers={'Idempotency-Key': 'pi-runtime-gate-1'},
    )
    assert gate.status_code == 200, gate.text
    assert gate.json()['status'] == 'succeeded'


def test_pi_product_run_rejects_non_public_pdf(client):
    uploaded = client.post('/api/v1/resources?name=input.csv', content=b'a,b\n1,2\n')
    assert uploaded.status_code == 201
    response = client.post(
        '/api/local/pi-contract-review',
        json={'resource_id': uploaded.json()['id'], 'objective': '不应运行', 'timeout_seconds': 30},
        headers={'Idempotency-Key': 'pi-runtime-invalid-1'},
    )
    assert response.status_code == 422
    assert response.json()['error']['code'] == 'PDF_RESOURCE_INVALID'


@pytest.mark.skipif(not (PI_ROOT / 'node_modules').is_dir(), reason='run npm ci in pi-adapter first')
def test_pi_gate_rejects_before_open_and_is_terminal_after_reject(client, app):
    uploaded = client.post(
        '/api/local/research-native/documents?name=contract-reject.pdf',
        content=b'%PDF-1.7\nfixture', headers={'content-type': 'application/pdf'},
    )
    body = {'resource_id': uploaded.json()['id'], 'objective': '审查', 'timeout_seconds': 30}
    created = client.post('/api/local/pi-contract-review', json=body,
                          headers={'Idempotency-Key': 'pi-reject-create-1'}).json()
    run_id = created['initial_run']['id']
    early = client.post(f'/api/local/pi-contract-review/{run_id}:gate',
                        json={'decision': 'pass', 'reason': '过早'},
                        headers={'Idempotency-Key': 'pi-reject-early-1'})
    assert early.status_code == 409

    app.state.service.execute(run_id)
    rejected = client.post(f'/api/local/pi-contract-review/{run_id}:gate',
                           json={'decision': 'reject', 'reason': 'Evidence 页码需要人工复核'},
                           headers={'Idempotency-Key': 'pi-reject-final-1'})
    assert rejected.status_code == 200 and rejected.json()['status'] == 'failed'
    again = client.post(f'/api/local/pi-contract-review/{run_id}:gate',
                        json={'decision': 'pass', 'reason': '不能绕过拒绝'},
                        headers={'Idempotency-Key': 'pi-reject-again-1'})
    assert again.status_code == 409


@pytest.mark.skipif(not (PI_ROOT / 'node_modules').is_dir(), reason='run npm ci in pi-adapter first')
def test_pi_cancel_before_execution_is_terminal_and_does_not_start_sidecar(client, app):
    uploaded = client.post(
        '/api/local/research-native/documents?name=contract-cancel.pdf',
        content=b'%PDF-1.7\nfixture', headers={'content-type': 'application/pdf'},
    )
    created = client.post('/api/local/pi-contract-review',
                          json={'resource_id': uploaded.json()['id'], 'objective': '取消', 'timeout_seconds': 30},
                          headers={'Idempotency-Key': 'pi-cancel-create-1'}).json()
    run_id = created['initial_run']['id']
    cancelled = client.post(f'/api/v1/runs/{run_id}:cancel', json={})
    assert cancelled.status_code == 200 and cancelled.json()['status'] == 'cancelled'
    app.state.service.execute(run_id)
    detail = client.get('/api/local/pi-contract-review/' + run_id).json()
    assert detail['run']['status'] == 'cancelled'
    assert detail['artifacts'] == []
