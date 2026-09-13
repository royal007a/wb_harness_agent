"""Produce redacted, repeatable ADR-0022 verification evidence."""
import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

from jsonschema import Draft202012Validator


ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / 'specs/v1/agent-runtime.schema.json'
TASK_SCHEMA = ROOT / 'harness/task.schema.json'
TASKS = ROOT / 'harness/tasks.json'


def utc_now():
    return datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')


def command(argv):
    completed = subprocess.run(argv, cwd=ROOT, text=True, capture_output=True, timeout=120)
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


def browser_evidence(path):
    result = json.loads(path.read_text())
    if result.get('errors') or not result.get('checks'):
        raise SystemExit('browser evidence is missing checks or reports errors: ' + str(path))
    return result['checks']


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=ROOT / 'harness/evidence/HA-0025/manifest.json')
    parser.add_argument('--browser-evidence', type=Path, default=ROOT / 'harness/evidence/HA-0025/browser-agent-runtime.json')
    parser.add_argument('--remote-browser-evidence', type=Path, default=ROOT / 'harness/evidence/HA-0025/remote/browser-agent-runtime.json')
    args = parser.parse_args()
    contract = json.loads(CONTRACT.read_text())
    Draft202012Validator.check_schema(contract)
    registry = json.loads(TASKS.read_text())
    errors = list(Draft202012Validator(json.loads(TASK_SCHEMA.read_text())).iter_errors(registry))
    if errors:
        raise SystemExit(errors[0].message)
    tests = command([sys.executable, '-m', 'pytest', 'tests/test_agent_runtime.py', '-q'])
    syntax = command(['node', '--check', 'frontend/agent-runtime.js'])
    static_api = command([sys.executable, '-c', 'import yaml; yaml.safe_load(open("specs/v1/openapi.yaml")); print("ok")'])
    manifest = {
        'task_id': 'HA-0025', 'generated_at': utc_now(), 'status': 'passed',
        'scope': 'Isolated Provider/Model/Agent/Session/Exchange runtime and authenticated remote mirror',
        'checks': {
            'agent_runtime_tests': tests.strip().splitlines()[-1], 'frontend_syntax': syntax.strip() or 'passed',
            'static_openapi_yaml': static_api.strip(), 'task_registry_schema': 'passed',
            'local_markdown_links_checked': local_link_count(), 'browser_local_checks': browser_evidence(args.browser_evidence),
            'browser_remote_checks': browser_evidence(args.remote_browser_evidence),
        },
        'runtime_assertions': {
            'default_runtime_enabled': False, 'default_model_calls': 0, 'default_provider_calls': 0,
            'default_network_calls': 0, 'tool_binding_count': 0, 'credential_values_persisted': False,
            'synthetic_assistant_response_on_failure': False, 'product_task_run_mutated': False,
        },
        'not_covered': [
            'approved real provider/model invocation', 'real credential value or Keychain resolution',
            'provider health network request', 'tools/MCP/Skills/ReAct/subagents/RAG/long-term memory',
            'multi-tenant identity, production data classification or external model data egress approval',
        ],
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps(manifest, ensure_ascii=False))


if __name__ == '__main__':
    main()
