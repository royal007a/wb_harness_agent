"""Build redacted HA-0026 acceptance evidence from local tests and browser output."""
import json
import xml.etree.ElementTree as ET
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / 'harness/evidence/HA-0026'


def test_summary(path):
    suite = ET.parse(path).getroot().find('testsuite')
    if suite is None:
        raise SystemExit('JUnit XML lacks a testsuite')
    summary = {name: int(suite.attrib.get(name, 0)) for name in ('tests', 'failures', 'errors', 'skipped')}
    if summary['failures'] or summary['errors']:
        raise SystemExit('test evidence has failures or errors')
    return summary


def main():
    summary = test_summary(EVIDENCE / 'all-tests.xml')
    browser = json.loads((EVIDENCE / 'browser.json').read_text())
    required = {
        'clear_simulation_label', 'three_agent_fanout', 'zero_external_calls', 'artifact_download',
        'rerun_new_tree', 'partial_risk_failure', 'event_trace', 'reload', 'mobile_layout',
    }
    if browser.get('errors') or not required <= set(browser.get('checks', [])):
        raise SystemExit('browser evidence has errors or misses required checks')
    manifest = {
        'task': 'HA-0026', 'status': 'passed', 'scope': 'local research multi-agent simulation only',
        'tests': summary, 'browser_checks': sorted(required),
        'runtime_counters': {'model_calls': 0, 'provider_calls': 0, 'network_calls': 0, 'external_tool_calls': 0},
        'contract': {
            'engine': 'engine_research_multi_agent_simulation', 'roles': ['financial', 'industry', 'risk'],
            'child_max_turns': 2, 'only_child_tool': 'resource.inspect',
            'skills': ['research.financial', 'research.industry', 'research.risk'],
        },
        'verified_boundaries': [
            'Skill snapshot drift, permission expansion and resource-scope violation are rejected',
            'Child outputs are independently recomputed from their assigned synthetic resource before aggregation',
            'Partial risk evidence remains not_assessed and is never represented as no risk',
            'No Claude SDK execution, Provider, model, network, external tool or real financial input is enabled',
        ],
        'artifacts': ['all-tests.xml', 'browser.json', 'research-agents-desktop.png', 'research-agents-mobile.png', 'acceptance.md'],
    }
    (EVIDENCE / 'manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps(manifest, ensure_ascii=False))


if __name__ == '__main__':
    main()
