"""Verify the HA-0022 plan/execution capability coverage audit without enabling a runtime."""
import hashlib
import json
import re
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from xml.etree import ElementTree

from fastapi.testclient import TestClient
from jsonschema import Draft202012Validator, FormatChecker


ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / 'harness/evidence/HA-0022'
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.app import create_app  # noqa: E402


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def junit_summary(path):
    root = ElementTree.parse(path).getroot()
    suites = [root] if root.tag == 'testsuite' else list(root.findall('testsuite'))
    return {name: sum(int(suite.attrib.get(name, '0')) for suite in suites)
            for name in ('tests', 'failures', 'errors', 'skipped')}


def verify_links():
    roots = [ROOT / 'README.md', *ROOT.glob('docs/**/*.md'), *ROOT.glob('exec-plans/**/*.md'),
             *ROOT.glob('harness/evidence/**/*.md')]
    missing = []
    for path in roots:
        for target in re.findall(r'(?<!\!)\[[^\]]+\]\(([^)#]+)(?:#[^)]+)?\)', path.read_text()):
            if '://' not in target and not target.startswith(('mailto:', '#')) and not (path.parent / target).resolve().exists():
                missing.append(f'{path.relative_to(ROOT)}: {target}')
    if missing:
        raise SystemExit('missing local Markdown links:\n' + '\n'.join(missing))
    return len(roots)


def main():
    control_doc = (ROOT / 'docs/harness/PLAN_REPLAN_CONTROL.md').read_text()
    debt = (ROOT / 'tech-debt-tracker.md').read_text()
    required_control_markers = (
        '图谱对应与能力覆盖', '固定选择', 'Action State', 'Gap State', '离线合同', 'TD-023',
    )
    required_debt_markers = (
        'HA-0014 已完成', 'ADR-0019/0020', 'TD-023', '动态 Agent Loop',
    )
    if any(marker not in control_doc for marker in required_control_markers):
        raise SystemExit('coverage matrix is incomplete')
    if any(marker not in debt for marker in required_debt_markers):
        raise SystemExit('technical debt is not aligned with coverage audit')

    task_schema = json.loads((ROOT / 'harness/task.schema.json').read_text())
    registry = json.loads((ROOT / 'harness/tasks.json').read_text())
    errors = list(Draft202012Validator(task_schema, format_checker=FormatChecker()).iter_errors(registry))
    if errors:
        raise SystemExit('task registry schema invalid: ' + '; '.join(error.message for error in errors))
    task = next(item for item in registry['tasks'] if item['id'] == 'HA-0022')
    if task['status'] not in {'running', 'completed'}:
        raise SystemExit('HA-0022 is not active or completed')

    with tempfile.TemporaryDirectory() as temporary:
        with TestClient(create_app(Path(temporary) / 'audit.db', run_worker=False), base_url='http://127.0.0.1') as client:
            health = client.get('/api/v1/health').json()
            engines = client.get('/api/v1/engines').json()['items']
            adapters = client.app.state.service.adapters
    if health['model_calls_enabled'] is not False or set(adapters) != {'engine_mock_analytics'}:
        raise SystemExit('audit accidentally observes a broader runtime capability')
    engine_states = {engine['id']: engine['status'] for engine in engines}
    if engine_states != {
        'engine_mock_analytics': 'available', 'engine_local_research_demo': 'available',
        'engine_smolagents_code': 'blocked', 'engine_claude': 'planned',
        'engine_deepagents': 'planned', 'engine_pi': 'planned',
    }:
        raise SystemExit('engine capability inventory changed without an audit update')

    summary = junit_summary(EVIDENCE / 'all-tests.xml')
    if summary['tests'] < 163 or summary['failures'] or summary['errors']:
        raise SystemExit('coverage audit regression evidence does not pass')
    links_checked = verify_links()
    artifacts = ('all-tests.xml', 'acceptance.md')
    manifest = {
        'task': 'HA-0022', 'checked_at': datetime.now(timezone.utc).isoformat(), 'status': 'passed',
        'scope': 'Plan / TAO / State / Replan capability coverage audit only',
        'coverage': {
            'matrix_markers': list(required_control_markers), 'technical_debt_markers': list(required_debt_markers),
            'local_markdown_files_checked': links_checked,
        },
        'runtime_inventory': {
            'adapters': sorted(adapters), 'model_calls_enabled': health['model_calls_enabled'],
            'engines': engine_states, 'model_calls': 0, 'network_calls_by_adapter': 0,
            'arbitrary_code_calls': 0,
        },
        'test_summary': summary,
        'artifacts': {name: {'sha256': sha256(EVIDENCE / name)} for name in artifacts},
    }
    (EVIDENCE / 'manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps({'task': manifest['task'], 'status': manifest['status'], 'tests': summary['tests'],
                      'links': links_checked, 'adapters': manifest['runtime_inventory']['adapters']}, ensure_ascii=False))


if __name__ == '__main__':
    main()
