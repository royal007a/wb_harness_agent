import json
from pathlib import Path
import subprocess
import sys

import pytest
from jsonschema import Draft202012Validator

from backend.execution_control import (choose_exit, evaluate_try, propagate_reliability, transition_replan,
                                       assess_replan_adapter, validate_claim_evidence, validate_plan_graph)
from adapters.local import LocalAnalyticsAdapter
from harness.checkpoint_restore_probe import DeterministicCheckpointProbeAdapter, run_probe


ROOT = Path(__file__).resolve().parents[1]
EVALUATOR = ROOT / 'harness/evaluate_execution_control.py'
FIXTURE = ROOT / 'fixtures/execution-control-evaluation-v1.json'
CONTRACT = json.loads((ROOT / 'specs/v1/execution-control.schema.json').read_text())


def validate(kind, value):
    schema = {'$ref': '#/$defs/' + kind, '$defs': CONTRACT['$defs']}
    errors = list(Draft202012Validator(schema).iter_errors(value))
    assert not errors, errors[0].message


def is_valid(kind, value):
    schema = {'$ref': '#/$defs/' + kind, '$defs': CONTRACT['$defs']}
    return Draft202012Validator(schema).is_valid(value)


def test_execution_control_fixture_is_schema_valid_and_repeatable(tmp_path):
    output = tmp_path / 'execution-control-evaluation.json'
    process = subprocess.run([
        sys.executable, str(EVALUATOR), '--fixture', str(FIXTURE), '--output', str(output),
    ], capture_output=True, text=True, timeout=5)
    assert process.returncode == 0, process.stderr
    report = json.loads(output.read_text())
    assert report['classification'] == 'synthetic_deidentified'
    assert report['case_count'] == 13
    assert report['failed_case_ids'] == []


def test_action_selection_never_bypasses_registration_or_hard_preconditions():
    snapshot = {
        'success_criteria_met': False, 'evidence_gate_passed': False,
        'retry_eligible': False, 'replan_eligible': False, 'core_gap_unresolvable': False,
        'candidate_actions': [
            {'id': 'resource.inspect', 'hard_preconditions': ['resource_registered'],
             'required_permissions': ['resource.inspect'], 'cost_units': 1},
            {'id': 'network.fetch', 'hard_preconditions': [],
             'required_permissions': ['network.fetch'], 'cost_units': 1},
        ],
        'registered_action_ids': ['resource.inspect'],
        'satisfied_preconditions': [], 'effective_permissions': ['resource.inspect'], 'remaining_budget': 1,
    }
    assert choose_exit(snapshot)['exit'] == 'interrupt'


def test_current_local_adapter_admits_only_to_the_separate_runtime_probe_gate():
    local = assess_replan_adapter(LocalAnalyticsAdapter().describe())
    assert local == {
        'adapter_id': 'local_analytics', 'adapter_version': '1.1.0', 'engine': 'engine_mock_analytics',
        'status': 'eligible_for_runtime_probe', 'missing_capabilities': [],
        'runtime_enabled': False,
    }
    probe_candidate = assess_replan_adapter({
        'adapter_id': 'adapter_probe', 'adapter_version': '1.0.0', 'engine': 'engine_probe',
        'capabilities': {
            'state.checkpoint': {'supported': True}, 'state.restore': True,
            'control.cancel': {'supported': True}, 'output.structured': True,
        },
    })
    assert probe_candidate['status'] == 'eligible_for_runtime_probe'
    assert probe_candidate['runtime_enabled'] is False


def test_isolated_checkpoint_probe_runs_try_confirm_restore_without_product_runtime():
    report = run_probe()
    assert report['adapter_admission']['status'] == 'eligible_for_runtime_probe'
    assert report['adapter_admission']['runtime_enabled'] is False
    assert report['replan_statuses'] == ['proposed', 'trying', 'awaiting_confirmation', 'confirmed']
    assert report['restored_next_node_id'] == 'node_publish'
    assert report['restored_completed_node_ids'] == ['node_inspect']
    assert report['model_calls'] == report['tool_calls'] == report['network_calls'] == 0
    assert report['product_run_created_or_restored'] is False
    adapter = DeterministicCheckpointProbeAdapter()
    checkpoint, payload = adapter.checkpoint({'next_node_id': 'node_publish', 'completed_node_ids': ['node_inspect']})
    for field in ('checkpoint_digest', 'state_digest', 'adapter_digest', 'resource_digest',
                  'effective_permissions_digest', 'remaining_limits_digest'):
        with pytest.raises(ValueError, match='mismatch'):
            adapter.restore({**checkpoint, field: 'b' * 64}, payload)


def test_reliability_invalidates_every_downstream_record_and_rejects_cycles():
    records = [
        {'id': 'evi_source', 'reliability': 'invalid', 'depends_on': []},
        {'id': 'clm_conclusion', 'reliability': 'verified', 'depends_on': ['evi_source']},
    ]
    assert propagate_reliability(records) == {'evi_source': 'invalid', 'clm_conclusion': 'invalid'}
    with pytest.raises(ValueError, match='cycle'):
        propagate_reliability([
            {'id': 'node_one', 'reliability': 'verified', 'depends_on': ['node_two']},
            {'id': 'node_two', 'reliability': 'verified', 'depends_on': ['node_one']},
        ])


def test_tcc_cancel_does_not_transition_a_terminal_replan_attempt():
    assert transition_replan('trying', 'cancel') == 'cancelled'
    with pytest.raises(ValueError, match='illegal'):
        transition_replan('confirmed', 'cancel')


def test_try_preflight_rejects_duplicate_dangling_and_cyclic_plan_graphs():
    assert validate_plan_graph([
        {'id': 'node_inspect', 'depends_on': []},
        {'id': 'node_publish', 'depends_on': ['node_inspect']},
    ]) is True
    with pytest.raises(ValueError, match='duplicate'):
        validate_plan_graph([{'id': 'node_a', 'depends_on': []}, {'id': 'node_a', 'depends_on': []}])
    with pytest.raises(ValueError, match='unknown'):
        validate_plan_graph([{'id': 'node_a', 'depends_on': ['node_missing']}])
    with pytest.raises(ValueError, match='cycle'):
        validate_plan_graph([
            {'id': 'node_a', 'depends_on': ['node_b']},
            {'id': 'node_b', 'depends_on': ['node_a']},
        ])
    context = {
        'checkpoint_reliability': 'verified',
        'adapter_capabilities': {'state.checkpoint': True, 'state.restore': True, 'control.cancel': True},
        'candidate_plan_digest_present': True, 'candidate_permissions': [], 'origin_permissions': [],
        'candidate_budget': 0, 'remaining_budget': 0, 'compatibility_digest_matches': True,
    }
    assert evaluate_try(context, [{'id': 'node_a', 'depends_on': ['node_a']}]) == {
        'passed': False, 'failure_codes': ['PLAN_GRAPH_INVALID'],
    }


def test_core_contract_objects_are_versioned_and_redacted_by_shape():
    stamp = '2026-09-13T12:00:00Z'
    sha = 'a' * 64
    plan = {
        'contract_version': 'plan-revision@1', 'id': 'plan_demo', 'task_id': 'task_demo',
        'revision': 1, 'based_on_plan_revision_id': None,
        'nodes': [{'id': 'node_inspect', 'action_id': 'resource.inspect', 'depends_on': [],
                   'hard_preconditions': ['resource_registered'], 'soft_preconditions': [],
                   'success_criteria': ['resource_validated'], 'evidence_requirements': ['source_hash'],
                   'risk': 'read', 'idempotency': 'required'}],
        'plan_digest': sha, 'created_at': stamp,
    }
    evidence = {
        'contract_version': 'evidence@1', 'id': 'evi_source', 'run_id': 'run_demo',
        'kind': 'resource', 'ref_id': 'res_demo', 'content_sha256': sha, 'reliability': 'verified',
        'validation_status': 'passed', 'data_class': 'Internal', 'created_at': stamp,
    }
    claim = {
        'contract_version': 'claim@1', 'id': 'clm_total', 'run_id': 'run_demo', 'kind': 'fact',
        'supporting_evidence_ids': ['evi_source'], 'contradicting_evidence_ids': [],
        'reliability': 'verified', 'status': 'supported', 'created_at': stamp,
    }
    gap = {
        'contract_version': 'gap@1', 'id': 'gap_source', 'run_id': 'run_demo', 'required_by': 'node_inspect',
        'type': 'resource', 'severity': 'core', 'resolvable_action_ids': ['resource.inspect'],
        'status': 'open', 'created_at': stamp,
    }
    checkpoint = {
        'contract_version': 'checkpoint-projection@1', 'checkpoint_id': 'ckpt_demo', 'run_id': 'run_demo',
        'reliability': 'verified', 'checkpoint_digest': sha, 'state_digest': sha, 'evidence_digest': sha,
        'gap_digest': sha, 'adapter_digest': sha, 'resource_digest': sha, 'effective_permissions_digest': sha,
        'remaining_limits_digest': sha, 'adapter_restore_supported': True, 'restorable': True, 'created_at': stamp,
    }
    replan = {
        'contract_version': 'replan-attempt@1', 'id': 'rpl_demo', 'origin_run_id': 'run_demo',
        'origin_plan_revision_id': 'plan_demo', 'failure_event_id': 'evt_demo',
        'root_cause_evidence_ids': ['evi_source'], 'root_cause_confidence': 'high',
        'rollback_checkpoint_id': 'ckpt_demo', 'replan_start_node_id': 'node_inspect',
        'invalidated_node_ids': ['node_inspect'], 'candidate_plan_revision_id': 'plan_next',
        'candidate_plan_digest': sha, 'try_result_digest': None, 'confirmation_binding_digest': None,
        'confirmed_run_id': None, 'status': 'proposed', 'created_at': stamp,
    }
    for kind, value in [('plan_revision', plan), ('evidence', evidence), ('claim', claim),
                        ('gap', gap), ('checkpoint_projection', checkpoint), ('replan_attempt', replan)]:
        validate(kind, value)
        assert 'objective' not in value and 'secret' not in value
    unsupported_claim = {**claim, 'supporting_evidence_ids': [], 'status': 'supported'}
    invalid_checkpoint = {**checkpoint, 'adapter_restore_supported': False}
    unbound_confirmation = {**replan, 'status': 'confirmed'}
    assert not is_valid('claim', unsupported_claim)
    assert not is_valid('checkpoint_projection', invalid_checkpoint)
    assert not is_valid('replan_attempt', unbound_confirmation)
    assert validate_claim_evidence(claim, {'evi_source': evidence}) is True
    with pytest.raises(ValueError, match='unverified'):
        validate_claim_evidence(claim, {'evi_source': {**evidence, 'reliability': 'dirty'}})
