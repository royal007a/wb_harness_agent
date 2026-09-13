"""Verify HA-0023's P0 decision brief without enabling a real Agent route."""
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
EVIDENCE = ROOT / 'harness/evidence/HA-0023'
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


def local_link_count():
    files = [ROOT / 'README.md', *ROOT.glob('docs/**/*.md'), *ROOT.glob('exec-plans/**/*.md'),
             *ROOT.glob('harness/evidence/**/*.md')]
    missing = []
    for path in files:
        for target in re.findall(r'(?<!\!)\[[^\]]+\]\(([^)#]+)(?:#[^)]+)?\)', path.read_text()):
            if '://' not in target and not target.startswith(('mailto:', '#')) and not (path.parent / target).resolve().exists():
                missing.append(f'{path.relative_to(ROOT)}: {target}')
    if missing:
        raise SystemExit('missing local Markdown links:\n' + '\n'.join(missing))
    return len(files)


def main():
    brief = (ROOT / 'docs/harness/P0_ACTIVATION_DECISION.md').read_text()
    p0 = (ROOT / 'docs/harness/P0_DATA_ANALYSIS.md').read_text()
    blocked = (ROOT / 'exec-plans/blocked/HA-0008-model-connection.md').read_text()
    probe = json.loads((ROOT / 'harness/evidence/HA-0007/probe.json').read_text())
    markers = ('一页结论', '请求确认的授权边界', '停止条件', '不随批准发生的事',
               '生产或数据处理授权', '不含明文')
    if any(marker not in brief for marker in markers):
        raise SystemExit('P0 decision brief misses a required safety boundary')
    if '至少准备四组固定 CSV' not in p0 or '状态：blocked' not in blocked:
        raise SystemExit('P0 source documents no longer match the decision brief')
    if probe.get('real_model') is not False or probe.get('mode') != 'scripted_model_real_sdk_real_vm':
        raise SystemExit('the development probe cannot support the stated P0 distinction')

    schema = json.loads((ROOT / 'harness/task.schema.json').read_text())
    registry = json.loads((ROOT / 'harness/tasks.json').read_text())
    errors = list(Draft202012Validator(schema, format_checker=FormatChecker()).iter_errors(registry))
    if errors:
        raise SystemExit('task registry schema invalid: ' + '; '.join(error.message for error in errors))
    task = next(item for item in registry['tasks'] if item['id'] == 'HA-0023')
    if task['status'] not in {'running', 'completed'}:
        raise SystemExit('HA-0023 is not active or completed')

    with tempfile.TemporaryDirectory() as temporary:
        with TestClient(create_app(Path(temporary) / 'brief.db', run_worker=False), base_url='http://127.0.0.1') as client:
            health = client.get('/api/v1/health').json()
            engines = {item['id']: item['status'] for item in client.get('/api/v1/engines').json()['items']}
            adapters = sorted(client.app.state.service.adapters)
    if health['model_calls_enabled'] is not False or adapters != ['engine_mock_analytics']:
        raise SystemExit('P0 decision brief is inconsistent with the current runtime inventory')
    if engines.get('engine_smolagents_code') != 'blocked' or engines.get('engine_claude') != 'planned':
        raise SystemExit('a real Agent route was enabled without an updated activation decision')

    summary = junit_summary(EVIDENCE / 'all-tests.xml')
    if summary['tests'] < 163 or summary['failures'] or summary['errors']:
        raise SystemExit('P0 decision brief regression evidence does not pass')
    links = local_link_count()
    artifacts = ('all-tests.xml', 'acceptance.md')
    manifest = {
        'task': 'HA-0023', 'checked_at': datetime.now(timezone.utc).isoformat(), 'status': 'passed',
        'scope': 'P0 CodeAct development-pilot activation decision brief only',
        'source_facts': {
            'p0_requires_four_fixture_categories': True,
            'ha_0008_blocked': True,
            'sdk_vm_probe_mode': probe['mode'],
            'sdk_vm_probe_real_model': probe['real_model'],
            'local_markdown_files_checked': links,
        },
        'runtime_inventory': {
            'adapters': adapters, 'model_calls_enabled': health['model_calls_enabled'], 'engines': engines,
            'model_calls': 0, 'network_calls_by_adapter': 0, 'arbitrary_code_calls': 0,
        },
        'test_summary': summary,
        'artifacts': {name: {'sha256': sha256(EVIDENCE / name)} for name in artifacts},
    }
    (EVIDENCE / 'manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps({'task': manifest['task'], 'status': manifest['status'], 'tests': summary['tests'],
                      'links': links, 'real_model': probe['real_model']}, ensure_ascii=False))


if __name__ == '__main__':
    main()
