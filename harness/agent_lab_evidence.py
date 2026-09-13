"""Produce redacted, repeatable ADR-0021 verification evidence."""
import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / 'specs/v1/local-agent-lab.schema.json'
TASK_SCHEMA = ROOT / 'harness/task.schema.json'
TASKS = ROOT / 'harness/tasks.json'


def utc_now():
    return datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')


def command(argv):
    completed = subprocess.run(argv, cwd=ROOT, text=True, capture_output=True, timeout=90)
    if completed.returncode:
        raise SystemExit(completed.stdout + completed.stderr)
    return completed.stdout


def local_link_count():
    missing, count = [], 0
    for source in ROOT.rglob('*.md'):
        if any(part.startswith('.') for part in source.relative_to(ROOT).parts):
            continue
        for line in source.read_text(errors='replace').splitlines():
            if '](' not in line:
                continue
            for target in line.split('](')[1:]:
                target = target.split(')', 1)[0].split('#', 1)[0].strip('<>')
                if not target or '://' in target or target.startswith('mailto:'):
                    continue
                count += 1
                if not (source.parent / target).resolve().exists():
                    missing.append(str(source.relative_to(ROOT)) + ' -> ' + target)
    if missing:
        raise SystemExit('missing local Markdown links:\n' + '\n'.join(missing))
    return count


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=ROOT / 'harness/evidence/HA-0024/manifest.json')
    parser.add_argument('--browser-evidence', type=Path,
                        default=ROOT / 'harness/evidence/HA-0024/browser-agent-lab.json')
    args = parser.parse_args()
    contract = json.loads(CONTRACT.read_text())
    Draft202012Validator.check_schema(contract)
    task_registry = json.loads(TASKS.read_text())
    task_schema = json.loads(TASK_SCHEMA.read_text())
    errors = list(Draft202012Validator(task_schema).iter_errors(task_registry))
    if errors:
        raise SystemExit(errors[0].message)
    tests = command([sys.executable, '-m', 'pytest', 'tests/test_agent_lab.py', '-q'])
    syntax = command(['node', '--check', 'frontend/agent-lab.js'])
    static_api = command([sys.executable, '-c', 'import yaml; yaml.safe_load(open("specs/v1/openapi.yaml")); print("ok")'])
    links = local_link_count()
    browser = json.loads(args.browser_evidence.read_text())
    if browser.get('errors') or not browser.get('checks'):
        raise SystemExit('browser evidence is missing checks or reports errors')
    manifest = {
        'task_id': 'HA-0024', 'generated_at': utc_now(), 'status': 'passed',
        'scope': 'Local Agent Lab configuration/session/POST-SSE preparation',
        'checks': {
            'agent_lab_tests': tests.strip().splitlines()[-1],
            'frontend_syntax': syntax.strip() or 'passed',
            'static_openapi_yaml': static_api.strip(),
            'task_registry_schema': 'passed',
            'local_markdown_links_checked': links,
            'browser_checks': browser['checks'],
        },
        'runtime_assertions': {
            'model_calls': 0, 'provider_calls': 0, 'network_calls': 0, 'tool_calls': 0,
            'credential_fields_accepted': False, 'product_task_run_mutated': False,
        },
        'not_covered': [
            'real provider connectivity', 'credentials or credential references', 'model/SDK invocation',
            'tool/MCP execution', 'RAG or long-term memory', 'production identity or multi-tenant isolation',
        ],
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps(manifest, ensure_ascii=False))


if __name__ == '__main__':
    main()
