import copy
from hashlib import sha256
import json
from pathlib import Path
import sys

import pytest

import backend.claude_research_admission as admission_module
from adapters.claude_research import assert_ready, configuration_from_request, runtime_status
from backend.analysis import Problem
from backend.claude_research_admission import (
    assert_public_pdf_binding,
    assert_source_binding,
    load,
    require_approved,
    runtime_status as admission_runtime_status,
    validate,
)
from backend.research_sources import SourcePolicy


ROOT = Path(__file__).resolve().parents[1]
CHECKED_IN = ROOT / 'harness/claude-research-admission.json'
REQUEST = {
    'company': '测试公司', 'stock_code': 'SZ000001', 'objective': '生成带来源的研究草稿。',
    'report_resource_id': 'res_' + 'a' * 64, 'timeout_seconds': 60, 'max_cost_minor': 300,
}
PDF = b'%PDF-1.4\npublic-fixture'


def approved():
    return {
        'schema_version': 'claude-research-admission@1', 'status': 'approved_for_l3_probe',
        'admission_enabled': True, 'model_calls': 0, 'external_calls': 0,
        'provider': {'kind': 'claude_agent_sdk_cli', 'cli_path': sys.executable,
                     'authentication_boundary': 'managed_by_claude_cli_not_read_by_harness'},
        'model': 'claude-test-controlled',
        'budget': {'currency': 'USD', 'max_cost_minor': 300, 'max_turns': 12, 'timeout_seconds': 60},
        'sources': {
            'allowed_domains': ['finance.example', 'search.example'],
            'search': {'endpoint': 'https://search.example/v1/search', 'credential_ref': 'keychain://harnessagent/research-search'},
            'financial': {'endpoint': 'https://finance.example/v1/financials', 'credential_ref': 'keychain://harnessagent/research-financial'},
        },
        'public_pdf': {'name': 'public-fixture.pdf', 'sha256': sha256(PDF).hexdigest(), 'data_class': 'Public'},
        'operators': {'cancel_owner': 'local_operator', 'rollback_owner': 'local_operator'},
        'blockers': [],
        'admission_evidence': {
            'approval_record': 'decision-record', 'data_egress_review': 'egress-review',
            'probe_runbook': 'probe-runbook', 'rollback_runbook': 'rollback-runbook',
        },
    }


def write(path, value):
    path.write_text(json.dumps(value))
    return path


def test_checked_in_admission_profile_is_fail_closed_and_secret_free():
    value = load(CHECKED_IN)
    assert value['status'] == 'not_admitted' and value['admission_enabled'] is False
    assert value['model_calls'] == value['external_calls'] == 0
    status = admission_runtime_status(CHECKED_IN)
    assert status['status'] == 'not_admitted' and status['admission_enabled'] is False
    with pytest.raises(Problem, match='尚未批准'):
        require_approved(CHECKED_IN)


@pytest.mark.parametrize('mutate', [
    lambda value: value.update({'admission_enabled': True}),
    lambda value: value['sources']['search'].update({'credential_ref': 'raw-secret'}),
    lambda value: value.update({'model': 'sk-not-a-secret-but-rejected'}),
    lambda value: value.update({'status': 'approved_for_l3_probe'}),
])
def test_incomplete_or_secret_like_admission_is_rejected(mutate):
    value = json.loads(CHECKED_IN.read_text())
    mutate(value)
    with pytest.raises(ValueError):
        validate(value)


def test_approved_profile_requires_deterministic_exact_domain_order():
    value = approved()
    value['sources']['allowed_domains'].reverse()
    with pytest.raises(ValueError, match='sorted order'):
        validate(value)


def test_approved_profile_binds_runtime_policy_pdf_and_budget(tmp_path, monkeypatch):
    path = write(tmp_path / 'admission.json', approved())
    monkeypatch.setattr(admission_module, 'ADMISSION_STATE', path)
    env = {
        'HARNESS_CLAUDE_RESEARCH_RUNTIME': 'enabled',
        'HARNESS_CLAUDE_RESEARCH_EXTERNAL_DATA': 'enabled',
        'HARNESS_CLAUDE_RESEARCH_CLI': sys.executable,
        'HARNESS_CLAUDE_RESEARCH_MODEL': 'claude-test-controlled',
        'HARNESS_CLAUDE_RESEARCH_ALLOWED_DOMAINS': 'finance.example,search.example',
        'HARNESS_CLAUDE_RESEARCH_SEARCH_ENDPOINT': 'https://search.example/v1/search',
        'HARNESS_CLAUDE_RESEARCH_FINANCIAL_ENDPOINT': 'https://finance.example/v1/financials',
        'HARNESS_CLAUDE_RESEARCH_SEARCH_CREDENTIAL_REF': 'keychain://harnessagent/research-search',
        'HARNESS_CLAUDE_RESEARCH_FINANCIAL_CREDENTIAL_REF': 'keychain://harnessagent/research-financial',
    }
    status = runtime_status(env)
    assert status['admission']['status'] == 'approved_for_l3_probe'
    assert 'admission_not_approved' not in status['blockers']
    assert 'admission_configuration_mismatch' not in status['blockers']
    mismatched = runtime_status({**env, 'HARNESS_CLAUDE_RESEARCH_MODEL': 'other-approved-looking-model'})
    assert 'admission_configuration_mismatch' in mismatched['blockers']
    config = configuration_from_request(REQUEST, env)
    profile = assert_ready(config, env)
    policy = SourcePolicy(True, ('finance.example', 'search.example'),
                          env['HARNESS_CLAUDE_RESEARCH_SEARCH_ENDPOINT'], env['HARNESS_CLAUDE_RESEARCH_FINANCIAL_ENDPOINT'],
                          env['HARNESS_CLAUDE_RESEARCH_SEARCH_CREDENTIAL_REF'], env['HARNESS_CLAUDE_RESEARCH_FINANCIAL_CREDENTIAL_REF'])
    assert_source_binding(profile, policy)
    assert_public_pdf_binding(profile, {'name': 'public-fixture.pdf', 'sha256': sha256(PDF).hexdigest(), 'data_class': 'Public'})
    with pytest.raises(Problem, match='超出'):
        assert_ready(configuration_from_request({**REQUEST, 'max_cost_minor': 301}, env), env)
    with pytest.raises(Problem, match='PDF'):
        assert_public_pdf_binding(profile, {'name': 'other.pdf', 'sha256': sha256(PDF).hexdigest(), 'data_class': 'Public'})


def test_invalid_profile_is_reported_as_closed_runtime_boundary(tmp_path):
    state = copy.deepcopy(approved())
    state['sources']['financial']['endpoint'] = 'http://finance.example/plain'
    path = write(tmp_path / 'invalid.json', state)
    assert admission_runtime_status(path) == {
        'schema_version': 'claude-research-admission@1', 'status': 'invalid_not_admitted',
        'admission_enabled': False, 'model_calls': 0, 'external_calls': 0,
        'blocker_count': 1, 'admission_digest': None, 'error': 'admission_profile_invalid',
    }
