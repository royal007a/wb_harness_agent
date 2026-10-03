import io
import json
import os
import socket
import zipfile

import pytest
from fastapi.testclient import TestClient

import backend.external_skills as external_skills
from backend.analysis import Problem
from backend.app import create_app
from backend.external_skill_sandbox import ExternalSkillSandbox, profile_args


MANIFEST = {
    'schema_version': 'external-skill-manifest@1',
    'skill_id': 'ext_json_echo',
    'version': '1.0.0',
    'entrypoint': 'entry.py',
    'runtime': 'python-stdlib@3.12',
    'capabilities': ['transform_json'],
}


def package(entry="def main(payload):\n    return {'echo': payload}\n", manifest=MANIFEST, extra=None):
    raw = io.BytesIO()
    with zipfile.ZipFile(raw, 'w', compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr('manifest.json', json.dumps(manifest))
        archive.writestr('entry.py', entry)
        if extra:
            archive.writestr(extra, 'no')
    return raw.getvalue()


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.delenv('HARNESS_EXTERNAL_SKILLS', raising=False)
    monkeypatch.setattr(external_skills, 'PACKAGE_ROOT', tmp_path / 'packages')
    app = create_app(tmp_path / 'external-skills.db', run_worker=False)
    with TestClient(app, base_url='http://127.0.0.1', client=('127.0.0.1', 45001)) as value:
        yield value


def register(client, raw=None, key='register-one'):
    response = client.post(
        '/api/local/external-skills/packages?source_label=reviewed-local-zip',
        content=raw or package(), headers={'Content-Type': 'application/zip', 'Idempotency-Key': key},
    )
    assert response.status_code == 201, response.text
    return response.json()


def test_default_gate_precedes_package_read_or_container_start(client):
    response = client.post('/api/local/external-skills/packages/extpkg_missing:execute', json={'input': {'x': 1}},
                           headers={'Idempotency-Key': 'blocked-execute'})
    assert response.status_code == 409
    assert response.json()['error']['code'] == 'EXTERNAL_SKILL_RUNTIME_DISABLED'
    assert client.get('/api/local/external-skills/packages').json()['items'] == []


def test_strict_zip_registration_and_idempotency(client):
    created = register(client)
    assert created['manifest'] == MANIFEST
    assert created['execution_count'] == 0
    replay = register(client, key='register-one')
    assert replay == created
    invalid = client.post('/api/local/external-skills/packages?source_label=reviewed-local-zip', content=package(extra='setup.py'),
                          headers={'Content-Type': 'application/zip', 'Idempotency-Key': 'invalid-package'})
    assert invalid.status_code == 422
    assert invalid.json()['error']['code'] == 'EXTERNAL_SKILL_PACKAGE_INVALID'
    assert client.get('/api/local/external-skills/packages').json()['items'] == [created]


def test_sensitive_package_content_and_unknown_fields_are_rejected(client):
    credential = "def main(payload):\n    return {'token': 'sk-not-a-real-secret-1234567890'}\n"
    rejected = client.post('/api/local/external-skills/packages?source_label=reviewed-local-zip', content=package(credential),
                           headers={'Content-Type': 'application/zip', 'Idempotency-Key': 'sensitive-package'})
    assert rejected.status_code == 422
    assert rejected.json()['error']['code'] == 'SENSITIVE_INPUT_REJECTED'
    rejected_label = client.post('/api/local/external-skills/packages?source_label=<script>', content=package(),
                                 headers={'Content-Type': 'application/zip', 'Idempotency-Key': 'bad-label'})
    assert rejected_label.status_code == 422


def test_execution_rechecks_digest_and_persists_sanitized_audit(client, monkeypatch):
    created = register(client)
    client.app.state.service.external_skills._enabled = True
    calls = []

    class FakeSandbox:
        def __init__(self, directory, payload):
            calls.append((directory, payload))
        def execute(self):
            return {'normalized': True}, {'image_id': 'sha256:' + 'a' * 64, 'duration_ms': 1,
                                          'profile_sha256': 'b' * 64, 'container_cleaned': True,
                                          'isolation_profile': 'external-skill-stdlib-v1'}

    client.app.state.service.external_skills.sandbox_cls = FakeSandbox
    endpoint = '/api/local/external-skills/packages/' + created['id'] + ':execute'
    response = client.post(endpoint, json={'input': {'name': 'Ada'}}, headers={'Idempotency-Key': 'run-one'})
    assert response.status_code == 200, response.text
    execution = response.json()
    assert execution['status'] == 'succeeded'
    assert execution['output'] == {'normalized': True}
    assert execution['audit']['container_cleaned'] is True
    assert len(calls) == 1 and calls[0][1] == {'name': 'Ada'}
    assert client.post(endpoint, json={'input': {'name': 'Ada'}}, headers={'Idempotency-Key': 'run-one'}).json() == execution
    assert len(calls) == 1
    stored = client.get('/api/local/external-skills/packages').json()['items'][0]
    assert stored['execution_count'] == 1
    entry = external_skills.PACKAGE_ROOT / created['content_sha256'] / 'entry.py'
    entry.chmod(0o644)
    entry.write_text("def main(payload): return {'tampered': True}\n")
    tampered = client.post(endpoint, json={'input': {'name': 'Grace'}}, headers={'Idempotency-Key': 'run-two'})
    assert tampered.status_code == 409
    assert tampered.json()['error']['code'] == 'EXTERNAL_SKILL_PACKAGE_TAMPERED'
    assert len(calls) == 1


@pytest.mark.parametrize('header', ['forwarded', 'x-forwarded-for', 'x-real-ip', 'x-forwarded-prefix', 'x-forwarded-proto'])
def test_proxy_cannot_register_or_execute_even_with_local_host(client, header):
    headers = {header: '/harness' if header == 'x-forwarded-prefix' else '127.0.0.1'}
    for path in ['/api/local/external-skills/packages', '/api/local/external-skills/packages/extpkg_x:execute']:
        response = client.post(path, headers=headers)
        assert response.status_code == 403
        assert response.json()['error']['code'] == 'EXTERNAL_SKILL_LOCAL_ONLY'
    assert client.get('/api/local/external-skills/runtime', headers=headers).status_code == 200


def test_non_loopback_peer_cannot_spoof_host(tmp_path):
    with TestClient(create_app(tmp_path / 'untrusted.db', run_worker=False),
                    base_url='http://127.0.0.1', client=('203.0.113.4', 45100)) as remote:
        assert remote.post('/api/local/external-skills/packages').status_code == 403


def test_execution_limit_fails_closed(client):
    runtime = client.app.state.service.external_skills
    runtime._execution_lock.acquire()
    try:
        response = client.post('/api/local/external-skills/packages/extpkg_x:execute', json={'input': {}},
                               headers={'Idempotency-Key': 'concurrent'})
        assert response.status_code == 429
        assert response.json()['error']['code'] == 'EXTERNAL_SKILL_BUSY'
    finally:
        runtime._execution_lock.release()


def test_backend_explicit_selection_and_no_fallback(monkeypatch):
    import sys
    import backend.sandbox as sandbox
    monkeypatch.setattr(sandbox.shutil, 'which', lambda name: sys.executable)
    monkeypatch.delenv('HARNESS_SANDBOX_BACKEND', raising=False)
    assert sandbox.docker_command()[1:] == ['--context', 'colima']
    monkeypatch.setenv('HARNESS_SANDBOX_BACKEND', 'linux-docker')
    monkeypatch.setattr(sandbox.sys, 'platform', 'linux')
    monkeypatch.setenv('DOCKER_HOST', 'tcp://untrusted.invalid:2375')
    assert sandbox.docker_command()[1:] == ['--host', 'unix:///var/run/docker.sock']
    monkeypatch.setenv('HARNESS_SANDBOX_BACKEND', 'automatic')
    with pytest.raises(Problem) as exc:
        sandbox.docker_command()
    assert exc.value.code == 'SANDBOX_BACKEND_INVALID'


@pytest.mark.skipif(os.environ.get('HARNESS_DOCKER_TESTS') != '1', reason='explicit real container probe')
@pytest.mark.parametrize('entry,expected', [
    ("def main(payload):\n    while True: pass\n", 'EXTERNAL_SKILL_TIMEOUT'),
    ("def main(payload):\n    import os\n    while True: os.write(1, b'x' * 4096)\n", 'EXTERNAL_SKILL_OUTPUT_LIMIT'),
    ("def main(payload):\n    open('/inputs/request.json', 'w').write('changed')\n    return {}\n", 'EXTERNAL_SKILL_EXECUTION_FAILED'),
    ("def main(payload):\n    open('/etc/forbidden', 'w').write('changed')\n    return {}\n", 'EXTERNAL_SKILL_EXECUTION_FAILED'),
])
def test_real_failures_cleanup_container_and_inputs(entry, expected):
    import shutil
    import tempfile
    from pathlib import Path
    from backend.sandbox import docker

    # Colima bind mounts must stay in its shared root; never execute entry on host.
    root = external_skills.ROOT / '.local'
    root.mkdir(exist_ok=True)
    directory = Path(tempfile.mkdtemp(prefix='ha0052-probe-', dir=root))
    directory.chmod(0o755)
    (directory / 'entry.py').write_text(entry)
    (directory / 'entry.py').chmod(0o444)
    observed = []

    class ObservedSandbox(ExternalSkillSandbox):
        def _read_result(self, ident):
            observed.append(ident)
            config = json.loads(docker(['inspect', ident]).stdout)[0]
            assert config['HostConfig']['LogConfig']['Type'] == 'none'
            assert config['HostConfig']['NetworkMode'] == 'none'
            assert config['HostConfig']['ReadonlyRootfs'] is True
            assert config['Config']['User'] == '65532:65532'
            return super()._read_result(ident)

    try:
        box = ObservedSandbox(directory, {'safe': True}, timeout_seconds=2)
        with pytest.raises(Problem) as exc:
            box.execute()
        assert exc.value.code == expected
        assert len(observed) == 1
        assert box.container_id is None and box._input_directory is None
        remaining = docker(['container', 'ls', '-aq', '--no-trunc', '--filter', 'id=' + observed[0]])
        assert remaining.returncode == 0 and not remaining.stdout.strip()
    finally:
        shutil.rmtree(directory)


@pytest.mark.skipif(os.environ.get('HARNESS_DOCKER_TESTS') != '1', reason='opt-in Colima external-Skill isolation probe')
def test_real_external_skill_container_isolation(client):
    # Provision the pinned image before the probe (build or verified SSH image
    # transfer). The test must not require registry access on an offline host.
    assert external_skills.image_id().startswith('sha256:')
    profile = profile_args('/skill', '/inputs', 'probe', 'sha256:' + 'a' * 64)
    assert '--network' in profile and profile[profile.index('--network') + 1] == 'none'
    assert '--read-only' in profile and '--cap-drop' in profile and '--user' in profile

    entry = '''def main(payload):
    import os, socket
    sock = socket.socket(); sock.settimeout(0.5)
    try:
        sock.connect(('1.1.1.1', 443))
    except OSError:
        network_denied = True
    else:
        network_denied = False
    return {
        'uid': os.getuid(),
        'host_visible': any(os.path.exists(p) for p in ['/Users/weberzhao', '/opt/harnessagent', '/root/.ssh']),
        'docker_socket': os.path.exists('/var/run/docker.sock'),
        'inherited_secret': bool(os.getenv('HARNESS_EXTERNAL_SKILL_TEST_SECRET')),
        'network_denied': network_denied,
        'input': payload,
    }
'''
    # Colima only bind-mounts its explicitly shared macOS roots.  Use the
    # project-local ignored staging root for this real VM probe, not pytest's
    # private /var temporary directory.
    external_skills.PACKAGE_ROOT = external_skills.ROOT / '.local/test-external-skill-packages'
    created = register(client, package(entry), key='register-real')
    client.app.state.service.external_skills._enabled = True
    previous = os.environ.get('HARNESS_EXTERNAL_SKILL_TEST_SECRET')
    os.environ['HARNESS_EXTERNAL_SKILL_TEST_SECRET'] = 'sentinel'
    try:
        response = client.post('/api/local/external-skills/packages/' + created['id'] + ':execute', json={'input': {'safe': 1}},
                               headers={'Idempotency-Key': 'run-real'})
    finally:
        if previous is None:
            del os.environ['HARNESS_EXTERNAL_SKILL_TEST_SECRET']
        else:
            os.environ['HARNESS_EXTERNAL_SKILL_TEST_SECRET'] = previous
    assert response.status_code == 200, response.text
    output = response.json()['output']
    assert output == {'uid': 65532, 'host_visible': False, 'docker_socket': False, 'inherited_secret': False,
                      'network_denied': True, 'input': {'safe': 1}}
