from harness.memory_graph_evaluation import CASESET_VERSION, run


def test_synthetic_memory_graph_evaluation_passes_and_declares_its_boundary():
    result = run()
    assert result['evaluation_version'] == CASESET_VERSION
    assert result['passed'] is True
    assert result['model_calls'] == 0 and result['external_calls'] == 0
    assert result['results']['two_hop_evidence_success'] == 1.0
    assert result['results']['cross_bank_leakage'] == 0.0
    assert 'not automatic entity extraction' in result['not_evidence'][0]
