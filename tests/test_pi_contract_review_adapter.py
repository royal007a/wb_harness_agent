from pathlib import Path

import pytest

from adapters.pi_contract_review import PiContractReviewAdapter
from adapters.contracts import AdapterRequest


PI_ROOT = Path(__file__).parents[1] / 'pi-adapter'


@pytest.mark.skipif(not (PI_ROOT / 'node_modules').is_dir(), reason='run npm ci in pi-adapter first')
def test_pi_contract_review_adapter_returns_cited_human_gate_finding():
    resource = {'id': 'resource-public-pdf-1', 'name': 'contract-fixture.pdf'}
    run = {'id': 'run_pi_adapter_1'}
    request = AdapterRequest(task={'objective': 'review'}, run=run, resource=resource, input_bytes=b'%PDF-1.7 fixture')
    events = []
    result = PiContractReviewAdapter().start_run(request, lambda kind, payload: events.append((kind, payload)), lambda: None)
    assert result.usage == {'model_calls': 0, 'cost_minor': 0, 'network_calls': 0}
    assert result.finding['status'] == 'needs_human'
    assert result.finding['gate']['status'] == 'needs_human'
    assert result.finding['evidence_refs'] == ['evidence://resource-public-pdf-1/clause-12.3/page-8']
    assert events[-1][0] == 'run.result.proposed'
    assert all(item[1].get('external_calls', 0) == 0 for item in events if isinstance(item[1], dict))


def test_pi_contract_review_adapter_rejects_non_pdf_before_sidecar():
    resource = {'id': 'resource-not-pdf', 'name': 'input.txt'}
    request = AdapterRequest(task={}, run={'id': 'run_invalid'}, resource=resource, input_bytes=b'plain text')
    with pytest.raises(Exception) as exc:
        PiContractReviewAdapter().start_run(request, lambda *_args: None, lambda: None)
    assert getattr(exc.value, 'code', None) == 'PDF_RESOURCE_INVALID'
