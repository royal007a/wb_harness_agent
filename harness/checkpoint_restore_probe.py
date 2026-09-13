"""Isolated deterministic checkpoint/restore probe; it is not a Product Run or adapter route."""
from __future__ import annotations

import copy
import hashlib
import json
import sys
from pathlib import Path

from jsonschema import Draft202012Validator


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.execution_control import (assess_replan_adapter, evaluate_try, transition_replan,
                                       validate_plan_graph)


CONTRACT = json.loads((ROOT / 'specs/v1/execution-control.schema.json').read_text())
SHA = 'a' * 64
STAMP = '2026-09-13T12:00:00Z'


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def validate(kind, value):
    schema = {'$ref': '#/$defs/' + kind, '$defs': CONTRACT['$defs']}
    errors = list(Draft202012Validator(schema).iter_errors(value))
    if errors:
        raise ValueError('invalid {}: {}'.format(kind, errors[0].message))


class DeterministicCheckpointProbeAdapter:
    """A local probe double, deliberately not registered in Service.adapters."""

    def describe(self):
        return {
            'adapter_id': 'checkpoint_probe', 'adapter_version': '0.1.0', 'protocol_version': '1.0.0',
            'engine': 'engine_checkpoint_probe', 'capabilities': {
                'state.checkpoint': {'supported': True, 'scope': 'opaque_probe_state'},
                'state.restore': {'supported': True, 'scope': 'same_adapter_version_only'},
                'control.cancel': {'supported': True, 'granularity': 'node_boundary'},
                'output.structured': True,
            },
        }

    def checkpoint(self, state):
        payload = copy.deepcopy(state)
        state_digest = digest(payload)
        binding = {
            'state_digest': state_digest, 'adapter_digest': digest(self.describe()), 'resource_digest': SHA,
            'effective_permissions_digest': SHA, 'remaining_limits_digest': SHA,
        }
        projection = {
            'contract_version': 'checkpoint-projection@1', 'checkpoint_id': 'ckpt_probe', 'run_id': 'run_origin',
            'reliability': 'verified', 'checkpoint_digest': digest(binding), **binding,
            'evidence_digest': SHA, 'gap_digest': SHA, 'adapter_restore_supported': True,
            'restorable': True, 'created_at': STAMP,
        }
        validate('checkpoint_projection', projection)
        return projection, payload

    def restore(self, projection, payload):
        validate('checkpoint_projection', projection)
        expected_binding = {
            'state_digest': digest(payload), 'adapter_digest': digest(self.describe()), 'resource_digest': SHA,
            'effective_permissions_digest': SHA, 'remaining_limits_digest': SHA,
        }
        if (not projection['restorable']
                or any(projection[key] != value for key, value in expected_binding.items())
                or projection['checkpoint_digest'] != digest(expected_binding)):
            raise ValueError('checkpoint restore binding mismatch')
        return copy.deepcopy(payload)


def run_probe():
    adapter = DeterministicCheckpointProbeAdapter()
    admission = assess_replan_adapter(adapter.describe())
    if admission['status'] != 'eligible_for_runtime_probe' or admission['runtime_enabled']:
        raise ValueError('probe adapter admission must stay offline')
    nodes = [
        {'id': 'node_inspect', 'depends_on': []},
        {'id': 'node_publish', 'depends_on': ['node_inspect']},
    ]
    validate_plan_graph(nodes)
    checkpoint, state = adapter.checkpoint({'next_node_id': 'node_publish', 'completed_node_ids': ['node_inspect']})
    try_result = evaluate_try({
        'checkpoint_reliability': checkpoint['reliability'], 'adapter_capabilities': adapter.describe()['capabilities'],
        'candidate_plan_digest_present': True, 'candidate_permissions': ['resource.inspect'],
        'origin_permissions': ['resource.inspect', 'artifact.publish'], 'candidate_budget': 1,
        'remaining_budget': 2, 'compatibility_digest_matches': True,
    }, nodes)
    if not try_result['passed']:
        raise ValueError('probe Try unexpectedly failed')
    statuses = ['proposed']
    statuses.append(transition_replan(statuses[-1], 'try'))
    statuses.append(transition_replan(statuses[-1], 'try_passed'))
    statuses.append(transition_replan(statuses[-1], 'confirm'))
    confirmation_binding = digest({
        'plan_digest': SHA, 'checkpoint_digest': checkpoint['checkpoint_digest'],
        'adapter_digest': checkpoint['adapter_digest'], 'resource_digest': checkpoint['resource_digest'],
        'effective_permissions_digest': checkpoint['effective_permissions_digest'],
        'remaining_limits_digest': checkpoint['remaining_limits_digest'],
    })
    attempt = {
        'contract_version': 'replan-attempt@1', 'id': 'rpl_probe', 'origin_run_id': 'run_origin',
        'origin_plan_revision_id': 'plan_origin', 'failure_event_id': 'evt_failure',
        'root_cause_evidence_ids': ['evi_probe'], 'root_cause_confidence': 'high',
        'rollback_checkpoint_id': checkpoint['checkpoint_id'], 'replan_start_node_id': 'node_publish',
        'invalidated_node_ids': ['node_publish'], 'candidate_plan_revision_id': 'plan_revised',
        'candidate_plan_digest': SHA, 'try_result_digest': digest(try_result),
        'confirmation_binding_digest': confirmation_binding, 'confirmed_run_id': 'run_restored',
        'status': statuses[-1], 'created_at': STAMP,
    }
    validate('replan_attempt', attempt)
    restored = adapter.restore(checkpoint, state)
    return {
        'mode': 'isolated_deterministic_checkpoint_restore_probe',
        'adapter_admission': admission, 'replan_statuses': statuses,
        'restored_next_node_id': restored['next_node_id'], 'restored_completed_node_ids': restored['completed_node_ids'],
        'model_calls': 0, 'tool_calls': 0, 'network_calls': 0,
        'product_run_created_or_restored': False, 'runtime_route_registered': False,
    }


def main():
    print(json.dumps(run_probe(), ensure_ascii=False, sort_keys=True))


if __name__ == '__main__':
    main()
