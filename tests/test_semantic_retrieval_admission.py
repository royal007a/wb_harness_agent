import json

import pytest
from fastapi.testclient import TestClient

from backend.app import create_app
from backend.memory import semantic_admission_status
from harness.verify_semantic_retrieval_admission import validate


def state(**overrides):
    value = {
        'schema_version': 'memory-semantic-admission@1', 'status': 'not_admitted', 'enabled': False,
        'model_calls': 0, 'external_calls': 0, 'blockers': ['missing required evidence'], 'admission_evidence': None,
    }
    value.update(overrides)
    return value


def write(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False))
    return path


def test_checked_in_admission_state_is_fail_closed():
    value = validate()
    assert value['status'] == 'not_admitted'
    assert value['enabled'] is False and value['model_calls'] == value['external_calls'] == 0
    runtime = semantic_admission_status()
    assert runtime == {
        'status': 'not_admitted', 'admission_enabled': False, 'runtime_enabled': False,
        'model_calls': 0, 'external_calls': 0, 'blocker_count': 3, 'error': None,
    }


@pytest.mark.parametrize(('value', 'valid'), [
    (state(enabled=True), False),
    (state(admission_evidence={'corpus_manifest': 'only-one-proof'}), False),
    (state(status='admitted', enabled=True, blockers=[], admission_evidence=None), False),
    (state(status='admitted', enabled=True, blockers=[], admission_evidence={
        'corpus_manifest': 'corpus@1', 'data_egress_review': 'review@1',
        'deletion_rebuild_test': 'delete@1', 'offline_evaluation': 'eval@1', 'latency_cost_baseline': 'cost@1',
    }, external_calls=1), True),
])
def test_invalid_or_admitted_gate_never_enables_runtime_without_implementation(tmp_path, value, valid):
    path = write(tmp_path / 'admission.json', value)
    if not valid:
        with pytest.raises(ValueError):
            validate(path)
        runtime = semantic_admission_status(path)
        assert runtime['status'] == 'invalid_not_admitted' and runtime['runtime_enabled'] is False
    else:
        assert validate(path)['status'] == 'admitted'
        runtime = semantic_admission_status(path)
        assert runtime['admission_enabled'] is True and runtime['runtime_enabled'] is False
        assert runtime['external_calls'] == 1


def test_runtime_exposes_gate_and_stays_disabled_after_restart(tmp_path):
    database = tmp_path / 'semantic-gate.db'
    with TestClient(create_app(database, False), base_url='http://127.0.0.1') as local:
        gate = local.get('/api/local/memory/runtime').json()['semantic_retrieval']
        assert gate['status'] == 'not_admitted'
        assert gate['admission_enabled'] is False and gate['runtime_enabled'] is False
    with TestClient(create_app(database, False), base_url='http://127.0.0.1') as restarted:
        gate = restarted.get('/api/local/memory/runtime').json()['semantic_retrieval']
        assert gate['status'] == 'not_admitted' and gate['runtime_enabled'] is False
