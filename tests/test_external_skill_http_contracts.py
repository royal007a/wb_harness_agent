"""HA-0073: local contract tests. No package entrypoint or Docker is executed."""
import copy
import io
import json
import sqlite3
import struct
import zipfile

import pytest
import yaml
from fastapi.testclient import TestClient
from jsonschema import Draft202012Validator
from referencing import Registry, Resource

from backend import external_skills
from backend.app import create_app
from backend.analysis import Problem
from backend.service import ROOT
from test_external_skills import MANIFEST, package
from test_product_contract_boundaries import snapshot
from test_product_http_contracts import FORMATS

BASE = '/api/local/external-skills'
OPS = [
    (BASE + '/runtime', 'get', '200', 'local_http_external_skill_runtime'),
    (BASE + '/packages', 'get', '200', 'local_http_external_skill_list'),
    (BASE + '/packages', 'post', '201', 'local_http_external_skill_package'),
    (BASE + '/packages/{package_id}:execute', 'post', '200', 'execution_result'),
]
IMAGE = 'sha256:' + 'a' * 64


class SyntheticSandbox:
    calls = None
    def __init__(self, directory, payload):
        self.payload = payload
        self.calls.append((directory, payload))
    def execute(self):
        return {'echo': self.payload}, {'isolation_profile': 'external-skill-stdlib-v1',
            'backend': 'colima', 'image_id': IMAGE, 'profile_sha256': 'b' * 64,
            'duration_ms': 1, 'container_cleaned': True}


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.delenv('HARNESS_EXTERNAL_SKILLS', raising=False)
    monkeypatch.delenv('HARNESS_AGENT_RUNTIME', raising=False)
    monkeypatch.setattr(external_skills, 'PACKAGE_ROOT', tmp_path / 'packages')
    monkeypatch.setattr(external_skills, 'image_id', lambda: IMAGE)
    monkeypatch.setattr(external_skills, 'sandbox_backend', lambda: 'colima')
    monkeypatch.setattr(SyntheticSandbox, 'calls', [])
    def forbidden(*args, **kwargs):
        pytest.fail('No real provider, Docker or package execution in this contract suite')
    monkeypatch.setattr('backend.external_skill_sandbox.docker', forbidden)
    monkeypatch.setattr('backend.external_skill_sandbox.docker_command', forbidden)
    with TestClient(create_app(tmp_path / 'skill73.db', False), base_url='http://127.0.0.1',
                    client=('127.0.0.1', 45173)) as c:
        c.app.state.service.external_skills.sandbox_cls = SyntheticSandbox
        c.app.state.service.agent_runtime.credentials.resolve = forbidden
        c.app.state.service.agent_runtime.adapters.require = forbidden
        c._transport.raise_server_exceptions = False
        yield c


def documents(c):
    file = ROOT / 'specs/v1/openapi.yaml'
    return [(c.get('/openapi.json').json(), False, {}),
            (yaml.safe_load(file.read_text()), True, {'$id': file.as_uri()})]


def contracts(c, op, status=None):
    path, method, success, name = OPS[op]
    sources, resources = {}, []
    for stem in ['external-skill-runtime', 'core-contracts']:
        file = ROOT / 'specs/v1' / (stem + '.schema.json')
        doc = json.loads(file.read_text())
        sources[stem] = doc
        resources += [(file.as_uri(), Resource.from_contents(doc)), (doc['$id'], Resource.from_contents(doc))]
    checks = []
    for doc, static, base in documents(c):
        p = path.removeprefix('/api').replace('{package_id}', '{packageId}') if static else path
        responses = doc['paths'][p][method]['responses']
        response = responses.get(status or success, responses.get('default', {}))
        if '$ref' in response:
            response = doc['components']['responses'][response['$ref'].split('/')[-1]]
        schema = response.get('content', {}).get('application/json', {}).get('schema', {})
        v = Draft202012Validator({**doc, **base, **schema}, registry=Registry().with_resources(resources),
                                  format_checker=FORMATS)
        assert not v.is_valid({}), ('empty response schema', op, status)
        checks.append(v)
    source = sources['core-contracts' if status else 'external-skill-runtime']
    name = 'local_http_error' if status else name
    assert name in source['$defs'], ('missing source contract', name)
    checks.append(Draft202012Validator({**source, '$ref': '#/$defs/' + name}, format_checker=FORMATS))
    return checks


def check(c, op, response, status):
    assert response.status_code == status, response.text
    for v in contracts(c, op, None if str(status) == OPS[op][2] else str(status)):
        v.validate(response.json())
        assert not v.is_valid({**response.json(), 'extra': True})
        if status >= 400:
            for field, invalid in [('retryable', True), ('request_id', 'wrong'), ('details', {})]:
                value = copy.deepcopy(response.json())
                value['error'][field] = invalid
                assert not v.is_valid(value)


def upload(c, raw=None, key='register73', label='fixture73'):
    return c.post(BASE + '/packages', params={'source_label': label},
                  content=package() if raw is None else raw,
                  headers={'Content-Type': 'application/zip', **({} if key is None else {'Idempotency-Key': key})})


def run(c, ident, key='run73', payload=None):
    return c.post(BASE + '/packages/' + ident + ':execute', json={'input': payload or {}},
                  headers={'Idempotency-Key': key})


@pytest.mark.parametrize('enabled', [False, True])
@pytest.mark.parametrize('available', [False, True])
@pytest.mark.parametrize('backend', ['colima', 'linux-docker'])
def test_runtime_states_are_exact_metadata_and_reads_do_not_write(client, monkeypatch, enabled, available, backend):
    runtime = client.app.state.service.external_skills
    runtime._enabled = enabled
    monkeypatch.setattr(external_skills, 'sandbox_backend', lambda: backend)
    probes = []
    def probe():
        probes.append(True)
        if not available:
            raise Problem('EXTERNAL_SKILL_IMAGE_MISSING', 'PRIVATE_IMAGE_PATH73', 503)
        return IMAGE
    monkeypatch.setattr(external_skills, 'image_id', probe)
    before = snapshot(client)
    result = client.get(BASE + '/runtime')
    check(client, 0, result, 200)
    value = result.json()
    assert value['runtime_enabled'] is enabled and value['backend'] == backend
    assert value['image_id'] == (IMAGE if available else None)
    assert value['blockers'] == ([] if enabled else ['external_skill_runtime_disabled']) + ([] if available else ['external_skill_image_missing'])
    listing = client.get(BASE + '/packages')
    check(client, 1, listing, 200)
    assert listing.json() == {'items': [], 'runtime': value}
    assert len(probes) == 2 and SyntheticSandbox.calls == [] and snapshot(client) == before
    assert 'PRIVATE_IMAGE_PATH73' not in result.text


def test_registration_execution_replay_count_and_tamper(client, monkeypatch):
    first = upload(client)
    check(client, 2, first, 201)
    value = first.json()
    assert value['manifest'] == MANIFEST and value['execution_count'] == 0
    directory = external_skills.PACKAGE_ROOT / value['content_sha256']
    assert sorted(p.name for p in directory.iterdir()) == ['entry.py', 'manifest.json']
    assert SyntheticSandbox.calls == []
    assert upload(client, key='dedup73').json() == value
    before = snapshot(client)
    assert upload(client).json() == value
    assert snapshot(client) == before
    client.app.state.service.external_skills._enabled = True
    executed = run(client, value['id'], payload={'x': 7})
    check(client, 3, executed, 200)
    assert executed.json()['output'] == {'echo': {'x': 7}} and len(SyntheticSandbox.calls) == 1
    listing = client.get(BASE + '/packages')
    check(client, 1, listing, 200)
    assert listing.json()['items'] == [{**value, 'execution_count': 1}]
    # Registration is a historical receipt, not the current execution counter.
    assert upload(client).json() == value
    client.app.state.service.external_skills._enabled = False
    monkeypatch.setattr(client.app.state.service.external_skills, '_verify_package',
                        lambda *args: pytest.fail('replay must not read package'))
    before = snapshot(client)
    assert run(client, value['id'], payload={'x': 7}).json() == executed.json()
    assert len(SyntheticSandbox.calls) == 1 and snapshot(client) == before
    conflict = run(client, value['id'], payload={'x': 8})
    check(client, 3, conflict, 409)
    assert snapshot(client) == before


@pytest.mark.parametrize('op', range(4))
def test_contract_rejects_empty_or_nested_invalid_result(client, op):
    item = upload(client).json()
    client.app.state.service.external_skills._enabled = True
    response = [lambda: client.get(BASE + '/runtime'), lambda: client.get(BASE + '/packages'),
                lambda: upload(client), lambda: run(client, item['id'])][op]()
    check(client, op, response, int(OPS[op][2]))
    value = response.json()
    cases = []
    if op == 0:
        for field, bad in [('network', 'allowed'), ('max_concurrency', 2), ('image_id', 'bad'), ('credentials', 'injected')]:
            cases.append({**value, field: bad})
        cases.append({**value, 'runtime_enabled': False, 'blockers': []})
    elif op in [1, 2]:
        for field, bad in [('execution_count', -1), ('content_sha256', 'A' * 64), ('storage', '/private/path')]:
            invalid = copy.deepcopy(value)
            (invalid['items'][0] if op == 1 else invalid)[field] = bad
            cases.append(invalid)
    else:
        for field, bad in [('image_id', 'bad'), ('container_cleaned', False), ('duration_ms', -1),
                           ('input_sha256', 'A' * 64), ('extra', 'private')]:
            invalid = copy.deepcopy(value)
            invalid['audit'][field] = bad
            cases.append(invalid)
    for v in contracts(client, op):
        for invalid in cases:
            assert not v.is_valid(invalid), (op, invalid)


def archive(manifest=b'{}', entry=b'def main(payload): return {}', compression=zipfile.ZIP_DEFLATED):
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, 'w', compression=compression) as z:
        z.writestr('manifest.json', manifest)
        z.writestr('entry.py', entry)
    return stream.getvalue()


def bad_zip(kind):
    if kind == 'deep_json':
        return archive(b'[' * 10000 + b']' * 10000)
    if kind == 'large_integer':
        return archive(b'{"number":' + b'1' * 10000 + b'}')
    if kind == 'utf8':
        return archive(b'\xff\xfe')
    if kind == 'extra':
        return package(extra='../extra.py')
    if kind == 'bzip2':
        return archive(json.dumps(MANIFEST).encode(), compression=zipfile.ZIP_BZIP2)
    raw = bytearray(package())
    central = raw.index(b'PK\x01\x02')
    if kind in {'encrypted', 'strong_encryption', 'patched_data'}:
        flag = {'encrypted': 1, 'strong_encryption': 64, 'patched_data': 32}[kind]
        struct.pack_into('<H', raw, 6, struct.unpack_from('<H', raw, 6)[0] | flag)
        struct.pack_into('<H', raw, central + 8, struct.unpack_from('<H', raw, central + 8)[0] | flag)
    elif kind == 'unsupported':
        struct.pack_into('<H', raw, 8, 99)
        struct.pack_into('<H', raw, central + 10, 99)
    elif kind == 'deflate':
        offset = 30 + struct.unpack_from('<H', raw, 26)[0] + struct.unpack_from('<H', raw, 28)[0]
        raw[offset] = 7  # Invalid DEFLATE block type, before CRC checking.
    elif kind == 'crc':
        struct.pack_into('<I', raw, central + 16, 0)
    elif kind == 'symlink':
        struct.pack_into('<I', raw, central + 38, 0o120777 << 16)
    return bytes(raw)


@pytest.mark.parametrize('kind', ['deep_json', 'large_integer', 'utf8', 'extra', 'bzip2', 'encrypted',
                                  'unsupported', 'deflate', 'crc', 'symlink', 'strong_encryption', 'patched_data'])
def test_bad_archive_is_422_before_any_persistence_or_execution(client, kind):
    before = snapshot(client)
    response = upload(client, bad_zip(kind))
    assert response.status_code == 422, response.text
    accepted_codes = {'EXTERNAL_SKILL_PACKAGE_INVALID', 'VALIDATION_ERROR'} if kind == 'deep_json' else {'EXTERNAL_SKILL_PACKAGE_INVALID'}
    assert response.json()['error']['code'] in accepted_codes
    assert snapshot(client) == before and SyntheticSandbox.calls == []
    assert not external_skills.PACKAGE_ROOT.exists()
    check(client, 2, response, 422)


@pytest.mark.parametrize('kind', ['key_missing', 'key_empty', 'key_long', 'oversize', 'media', 'label', 'missing_label'])
def test_upload_http_boundaries(client, kind):
    before = snapshot(client)
    if kind in {'key_missing', 'key_empty', 'key_long'}:
        response = upload(client, key={'key_missing': None, 'key_empty': '', 'key_long': 'k' * 129}[kind])
    elif kind == 'oversize':
        response = upload(client, b'x' * (128 * 1024 + 1))
    elif kind == 'media':
        response = client.post(BASE + '/packages?source_label=x', content=b'zip', headers={'Content-Type': 'text/plain'})
    elif kind == 'label':
        response = upload(client, label='<script>')
    else:
        response = client.post(BASE + '/packages', content=package(), headers={'Content-Type': 'application/zip'})
    expected = 413 if kind == 'oversize' else 415 if kind == 'media' else 422
    assert response.status_code == expected
    assert snapshot(client) == before and SyntheticSandbox.calls == []
    check(client, 2, response, expected)


@pytest.mark.parametrize('mode', ['disabled', 'missing', 'busy', 'tampered', 'sandbox_failure'])
def test_execution_errors_and_lock_release(client, monkeypatch, mode):
    item = upload(client).json()
    runtime = client.app.state.service.external_skills
    runtime._enabled = mode != 'disabled'
    ident = item['id']
    expected = {'disabled': 409, 'missing': 404, 'busy': 429, 'tampered': 409, 'sandbox_failure': 503}[mode]
    if mode == 'disabled':
        monkeypatch.setattr(runtime, '_verify_package', lambda *args: pytest.fail('disabled must not read package'))
        monkeypatch.setattr(runtime.store, 'external_skill_package', lambda *args: pytest.fail('disabled must not lookup package'))
    elif mode == 'missing':
        ident = 'extpkg_' + '0' * 32
    elif mode == 'busy':
        runtime._execution_lock.acquire()
    elif mode == 'tampered':
        file = external_skills.PACKAGE_ROOT / item['content_sha256'] / 'entry.py'
        file.chmod(0o644)
        file.write_text('tampered fixture')
    else:
        monkeypatch.setattr(SyntheticSandbox, 'execute', lambda self: (_ for _ in ()).throw(
            Problem('EXTERNAL_SKILL_START_FAILED', 'fixed public error', 503)))
    before = snapshot(client)
    try:
        response = run(client, ident)
        assert response.status_code == expected, response.text
        assert snapshot(client) == before
        check(client, 3, response, expected)
    finally:
        if mode == 'busy':
            runtime._execution_lock.release()
    assert not runtime._execution_lock.locked()


@pytest.mark.parametrize('stage', ['registration', 'execution'])
def test_database_failure_rolls_back_and_retry_is_explicit(client, stage):
    runtime = client.app.state.service.external_skills
    runtime._enabled = True
    item = upload(client).json() if stage == 'execution' else None
    table = 'external_skill_executions' if stage == 'execution' else 'idempotency'
    with runtime.store.transaction() as db:
        db.execute('CREATE TRIGGER failure73 BEFORE INSERT ON ' + table +
                   " BEGIN SELECT RAISE(ABORT, 'PRIVATE_DB_PATH73'); END")
    before = snapshot(client)[1]
    response = run(client, item['id']) if item else upload(client)
    assert response.status_code == 500 and 'PRIVATE_DB_PATH73' not in response.text
    assert snapshot(client)[1] == before
    assert not runtime._execution_lock.locked()
    check(client, 3 if item else 2, response, 500)
    with runtime.store.transaction() as db:
        db.execute('DROP TRIGGER failure73')
    result = run(client, item['id']) if item else upload(client)
    check(client, 3 if item else 2, result, 200 if item else 201)
    if item:
        assert len(SyntheticSandbox.calls) == 2  # Retry may re-execute, not exactly-once.
    else:
        assert len(list(external_skills.PACKAGE_ROOT.iterdir())) == 1


def test_restart_preserves_history_and_reads_do_not_execute(client, tmp_path):
    item = upload(client, key='k' * 128).json()
    runtime = client.app.state.service.external_skills
    runtime._enabled = True
    result = run(client, item['id']).json()
    db_path = tmp_path / 'skill73.db'
    client.__exit__(None, None, None)
    with TestClient(create_app(db_path, False), base_url='http://127.0.0.1',
                    client=('127.0.0.1', 45174)) as restored:
        restored.app.state.service.external_skills.sandbox_cls = SyntheticSandbox
        before = snapshot(restored)
        assert run(restored, item['id']).json() == result
        assert upload(restored, key='k' * 128).json() == item
        listing = restored.get(BASE + '/packages')
        check(restored, 1, listing, 200)
        assert listing.json()['items'][0]['execution_count'] == 1
        assert len(SyntheticSandbox.calls) == 1 and snapshot(restored) == before


def test_unexpected_zip_parser_fault_is_not_hidden(client, monkeypatch):
    raw = package()
    def fault(*args, **kwargs):
        raise RuntimeError('PRIVATE_PROGRAM_BUG73')
    monkeypatch.setattr(external_skills.zipfile, 'ZipFile', fault)
    before = snapshot(client)
    result = upload(client, raw)
    assert result.status_code == 500 and 'PRIVATE_PROGRAM_BUG73' not in result.text
    assert snapshot(client) == before
    check(client, 2, result, 500)


@pytest.mark.parametrize('fault_type', [ValueError, RecursionError])
def test_manifest_parser_limit_failure_is_an_input_error(client, monkeypatch, fault_type):
    raw = package()
    original = external_skills.json.loads
    def limited(value, *args, **kwargs):
        if isinstance(value, str) and value == json.dumps(MANIFEST):
            raise fault_type('PRIVATE_PARSER_LIMIT73')
        return original(value, *args, **kwargs)
    monkeypatch.setattr(external_skills.json, 'loads', limited)
    before = snapshot(client)
    result = upload(client, raw)
    check(client, 2, result, 422)
    assert result.json()['error']['code'] == 'EXTERNAL_SKILL_PACKAGE_INVALID'
    assert 'PRIVATE_PARSER_LIMIT73' not in result.text
    assert snapshot(client) == before and not SyntheticSandbox.calls


@pytest.mark.parametrize('body', [{'input': {}, 'extra': True}, {'input': []}, {}, [], {'input': {str(i): i for i in range(33)}}])
def test_execute_request_is_strict_before_gate_or_execution(client, body):
    before = snapshot(client)
    result = client.post(BASE + '/packages/extpkg_' + 'a' * 32 + ':execute', json=body,
                         headers={'Idempotency-Key': 'body73'})
    check(client, 3, result, 422)
    assert snapshot(client) == before and not SyntheticSandbox.calls


def test_declared_parameters_and_error_branches_match_source(client):
    source = external_skills.CONTRACT
    for doc, static, _ in documents(client):
        for path, method, _, _ in OPS:
            p = path.removeprefix('/api').replace('{package_id}', '{packageId}') if static else path
            operation = doc['paths'][p][method]
            expected = {'$ref': '#/components/responses/LocalProductError'} if static else {
                '$ref': '#/components/schemas/local_http_error'}
            for status in ['default'] + (['422'] if '422' in operation['responses'] else []):
                assert status in operation['responses'], ('missing declared error response', p, method, status)
                value = operation['responses'][status]
                assert (value if static else value['content']['application/json']['schema']) == expected
            if method == 'post':
                parameters = [doc['components']['parameters'][p['$ref'].split('/')[-1]] if '$ref' in p else p
                              for p in operation['parameters']]
                key = next(p for p in parameters if p['name'] == 'Idempotency-Key')
                assert key['required'] and key['schema']['minLength'] == 1 and key['schema']['maxLength'] == 128
        p = '/local/external-skills/packages' if static else BASE + '/packages'
        label = next(p for p in doc['paths'][p]['post']['parameters'] if p.get('name') == 'source_label')
        assert label['required']
        assert label['schema']['$ref'].endswith('/package_registration/properties/source_label')
    assert source['$defs']['package_registration']['properties']['source_label']['maxLength'] == 160


def test_stored_package_boundary_keys_and_labels(client):
    first = upload(client, archive(json.dumps(MANIFEST).encode(), compression=zipfile.ZIP_STORED), key='k' * 128, label='a' * 160)
    check(client, 2, first, 201)
    before = snapshot(client)
    check(client, 2, upload(client, label='a' * 161), 422)
    client.app.state.service.external_skills._enabled = True
    check(client, 3, run(client, first.json()['id'], key='k' * 129), 422)
    assert snapshot(client) == before and not SyntheticSandbox.calls
    check(client, 3, run(client, first.json()['id'], key='k' * 128), 200)
