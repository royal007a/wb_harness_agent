"""HA-0093: one credential-shape definition for every input boundary."""
import importlib
from pathlib import Path

import pytest

from backend.sensitive_patterns import CREDENTIAL_SHAPE
from test_dsh_payment_findings import client  # noqa: F401

ROOT = Path(__file__).resolve().parents[1]
MODULES = ['agent_runtime', 'agent_lab', 'team_security', 'external_skills', 'memory']
CREDENTIALS = ['password=SYNTH_hunter2', 'Password: SYNTH_x', 'api_key=SYNTH', 'client-secret: SYNTH',
               'access_token=SYNTH', 'refresh token: SYNTH', 'sk-SYNTH0123456789', 'AKIA0123456789ABCDEF']
BENIGN = ['乙方应在验收合格后30天内付款。', '密码由甲方另行通知。', 'passwordless 登录方案', 'skeleton key',
          'task-0123456789abc']


@pytest.mark.parametrize('module', MODULES)
def test_every_boundary_uses_the_shared_pattern(module):
    assert importlib.import_module('backend.' + module).SENSITIVE_INPUT is CREDENTIAL_SHAPE


def test_no_module_keeps_a_private_copy():
    owners = [p.relative_to(ROOT).as_posix() for p in (ROOT / 'backend').rglob('*.py')
              if 'refresh[_ -]?token' in p.read_text()]
    assert owners == ['backend/sensitive_patterns.py']


@pytest.mark.parametrize('text', CREDENTIALS)
def test_credential_shapes_match(text):
    assert CREDENTIAL_SHAPE.search(text)


@pytest.mark.parametrize('text', BENIGN)
def test_contract_text_is_not_rejected(text):
    assert not CREDENTIAL_SHAPE.search(text)


def test_dsh_rejects_password_shaped_document_before_any_run(client):
    body = dict(objective='核对付款条件', document='第1条 付款\n验收合格后30天内付款。\npassword=SYNTH_hunter2',
                public_data_confirmed=True, mode='integration_probe', template='payment_terms')
    response = client.post('/api/local/dsh/runs', json=body, headers={'Idempotency-Key': 'pw'})
    assert response.status_code == 422 and response.json()['error']['code'] == 'SENSITIVE_INPUT_REJECTED'
    assert 'SYNTH_hunter2' not in response.text
    assert client.get('/api/local/dsh/runs').json()['items'] == []
