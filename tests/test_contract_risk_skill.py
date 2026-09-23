import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).parents[1]


def test_contract_risk_skill_emits_human_gated_cited_candidate():
    preview = {
        'schema_version': 'pi-contract-pipeline-preview@1',
        'resource_id': 'res_demo123', 'source_sha256': 'a' * 64,
        'classification': {'focus_areas': ['违约责任']},
        'chunks': [{'index': 0, 'text_sha256': 'b' * 64}],
        'security': {'status': 'clear'},
    }
    script = ROOT / 'skills/contract-risk-review/scripts/review_preview.py'
    result = subprocess.run([sys.executable, str(script)], input=json.dumps(preview), text=True, capture_output=True, check=True)
    finding = json.loads(result.stdout)
    assert finding['status'] == 'needs_human'
    assert finding['risk_level'] == 'medium'
    assert finding['evidence_refs'] == ['evidence://res_demo123/chunk-0/' + 'b' * 64]
    assert finding['model_calls'] == finding['external_calls'] == 0
