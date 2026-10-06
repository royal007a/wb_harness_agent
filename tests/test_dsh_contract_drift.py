"""HA-0112: the plugin's declared tool contract and the platform's checks must not drift
(jikesummary 护栏三明治: 契约漂移 — guard and tool from one versioned contract)."""
import json
import re
import shutil
import subprocess
import uuid
from pathlib import Path

import pytest

from backend.dsh_context import CONTEXT_WINDOW
from backend.dsh_findings import SLOTS
from backend.dsh_runtime import SEARCH_PAGE
from backend.dsh_provider import MODEL, parse_response
from test_dsh_adversarial import response
from test_dsh_payment_findings import client, submit  # noqa: F401

ROOT = Path(__file__).resolve().parents[1]
PLUGIN = ROOT / 'dsh-adapter/platform-plugin.mjs'


@pytest.fixture(scope='module')
def declared():
    node = shutil.which('node')
    if not node or not (ROOT / 'dsh-adapter/node_modules').exists():
        pytest.skip('pinned DSH dependencies are not installed')
    script = ("import('./platform-plugin.mjs').then(m => console.log(JSON.stringify(Object.fromEntries("
              "Object.entries(m.TOOLS).map(([k, v]) => [k, {description: v.description, parameters: "
              "Object.fromEntries(Object.entries(v.parameters).map(([p, s]) => [p, {type: s.type, required: !!s.required}]))}])))))")
    out = subprocess.run([node, '--input-type=module', '-e', script], cwd=ROOT / 'dsh-adapter',
                         capture_output=True, text=True, timeout=60, check=True)
    return json.loads(out.stdout)


def test_findings_slots_match(declared):
    params = declared['submit_findings']['parameters']
    assert {k for k, v in params.items() if v['required']} == set(SLOTS)
    assert set(params) == set(SLOTS) | {'gaps'}


def test_search_page_and_context_window_match(declared):
    assert f'at most {SEARCH_PAGE} ' in declared['search_document']['description']
    window = re.search(r'contextWindow:\s*(\d+)', PLUGIN.read_text())
    assert window and int(window.group(1)) == CONTEXT_WINDOW


def _first_result(client, name, args):
    """Drive the platform gateway directly: the SDK validates declared schemas itself and
    would never forward an undeclared/missing field, so the platform check is tested alone."""
    ident = submit(client, template='free', document='第1条 付款\n验收后30天付款。', key=uuid.uuid4().hex)
    rt = client.app.state.service.dsh
    async def send(*_):
        return parse_response(response(calls=[(name, args)]))
    rt.send_probe = send
    def probe(prompt, root, model, model_call, tool_call, emit, check, **_):
        receipt = model_call({'crossing_id': 'm_1', 'request': {
            'model': MODEL, 'purpose': 'primary', 'messages': [],
            'tools': [{'name': 'read_clause'}, {'name': 'search_document'}]}})
        tool_call({'crossing_id': receipt['value']['tool_calls'][0]['id'],
                   'request': {'name': name, 'arguments': args}})
        return None
    rt.adapter.run = probe
    rt.execute(ident)
    run = rt.detail(ident)['run']
    accepted = any(e['event_type'] == 'dsh.tool.completed' for e in rt.store.events(ident))
    return run, accepted


@pytest.mark.parametrize('name', ['search_document', 'read_clause'])
def test_platform_accepts_exactly_the_declared_parameters(client, declared, name):
    params = declared[name]['parameters']
    sample = {'query': '付款', 'offset': 0, 'clause_id': 'clause-1'}
    required = {k: sample[k] for k, v in params.items() if v['required']}
    full = {k: sample[k] for k in params}
    assert _first_result(client, name, required)[1] is True
    assert _first_result(client, name, full)[1] is True
    run, accepted = _first_result(client, name, dict(full, undeclared='x'))
    assert not accepted and run['exit_reason'] == 'DSH_TOOL_INPUT'
    for key in required:                                   # every declared-required field is enforced
        run, accepted = _first_result(client, name, {k: v for k, v in full.items() if k != key})
        assert not accepted and run['exit_reason'] == 'DSH_TOOL_INPUT'
