import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.app import create_app
from backend.pi_admission import load, require_approved, runtime_status, validate


ROOT = Path(__file__).parents[1]


@pytest.fixture
def client(tmp_path):
    app = create_app(tmp_path / 'pi-admission.db', run_worker=False)
    with TestClient(app, base_url='http://127.0.0.1') as test_client:
        yield test_client


def test_default_pi_admission_is_valid_and_disabled():
    profile = load()
    status = runtime_status()
    assert profile['status'] == 'not_admitted'
    assert status['admission_enabled'] is False
    assert status['model_calls'] == 0 and status['external_calls'] == 0
    assert status['blocker_count'] >= 8
    with pytest.raises(Exception) as exc:
        require_approved()
    assert getattr(exc.value, 'code', None) == 'PI_ADMISSION_NOT_APPROVED'


def test_pi_admission_http_status_is_read_only(client):
    response = client.get('/api/local/pi/runtime')
    assert response.status_code == 200
    body = response.json()
    assert body['status'] == 'not_admitted'
    assert body['admission_enabled'] is False
    assert body['model_calls'] == 0 and body['external_calls'] == 0


def test_pi_admission_rejects_secret_and_incomplete_approval():
    value = json.loads((ROOT / 'harness/pi-admission.json').read_text())
    with pytest.raises(ValueError):
        validate({**value, 'blockers': [], 'provider': {'kind': 'pi_sidecar', 'package': 'pi',
                                                        'authentication_boundary': 'managed_at_platform_transport_not_read_by_pi'},
                  'model': 'sk-super-secret'})


def test_pi_admission_approval_requires_exact_endpoint_and_keychain_ref():
    value = json.loads((ROOT / 'harness/pi-admission.json').read_text())
    approved = {**value, 'status': 'approved_for_l3_probe', 'admission_enabled': True,
                'provider': {'kind': 'pi_sidecar', 'package': '@earendil-works/pi-agent-core@0.87.1',
                             'authentication_boundary': 'managed_at_platform_transport_not_read_by_pi'},
                'model': 'approved-model',
                'budget': {'currency': 'USD', 'max_cost_minor': 100, 'max_turns': 4, 'timeout_seconds': 60},
                'sources': {'allowed_domains': ['example.com'],
                            'search': {'endpoint': 'https://example.com/search', 'credential_ref': 'keychain://harnessagent/search'},
                            'financial': {'endpoint': 'https://example.com/financial', 'credential_ref': 'keychain://harnessagent/financial'}},
                'public_pdf': {'name': 'contract.pdf', 'sha256': 'a' * 64, 'data_class': 'Public'},
                'operators': {'cancel_owner': 'ops-a', 'rollback_owner': 'ops-b'}, 'blockers': [],
                'admission_evidence': {'approval_record': 'approval.md', 'data_egress_review': 'egress.md',
                                       'probe_runbook': 'probe.md', 'rollback_runbook': 'rollback.md'}}
    assert validate(approved)['status'] == 'approved_for_l3_probe'
    with pytest.raises(ValueError):
        validate({**approved, 'sources': {**approved['sources'], 'search': {'endpoint': 'https://other.example/search', 'credential_ref': 'keychain://harnessagent/search'}}})
