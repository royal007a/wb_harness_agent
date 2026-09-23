import json
import subprocess
import sys
from pathlib import Path

from harness.pi_contract_tui import render_event


ROOT = Path(__file__).resolve().parents[1]


def test_tui_renders_metadata_only_events_without_contract_text():
    preview = render_event('preview', {'classification': {'contract_type': '技术服务'}, 'chunks': [{'index': 0}], 'security': {'status': 'clear'}})
    finding = render_event('finding', {'risk_level': 'high', 'status': 'needs_human', 'method': 'deterministic_skill_baseline@1', 'evidence_refs': ['evidence://res_a/chunk-0/abc'], 'recommendation': '请人工复核'})
    done = render_event('done', {'model_calls': 0, 'external_calls': 0})
    assert 'chunk-0' in preview and '合同正文' not in preview
    assert 'needs_human' in finding and 'Evidence' in finding
    assert 'model_calls=0' in done


def test_tui_cli_renders_jsonl(tmp_path):
    source = tmp_path / 'events.jsonl'
    source.write_text(json.dumps({'event': 'done', 'data': {'model_calls': 0, 'external_calls': 0}}) + '\n')
    result = subprocess.run([sys.executable, str(ROOT / 'harness/pi_contract_tui.py'), '--input', str(source)], capture_output=True, text=True, check=True)
    assert '完成' in result.stdout and 'external_calls=0' in result.stdout
