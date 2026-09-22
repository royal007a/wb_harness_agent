from harness.memory_context_evaluation import CASESET_VERSION, run


def test_synthetic_memory_context_evaluation_passes_and_declares_its_boundary():
    result = run()
    assert result['evaluation_version'] == CASESET_VERSION
    assert result['passed'] is True
    assert result['model_calls'] == 0 and result['external_calls'] == 0
    assert result['results']['critical_fact_recall_at_12'] == 1.0
    assert result['results']['cross_bank_leakage'] == 0.0
    assert 'not semantic/vector retrieval' in result['not_evidence'][0]
