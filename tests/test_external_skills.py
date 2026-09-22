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
    monkeypatch.setattr(external_skills, 'PACKAGE_ROOT', tmp_path / 'packages')
    app = create_app(tmp_path / 'external-skills.db', run_worker=False)
    with TestClient(app, base_url='http://127.0.0.1') as value:
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


@pytest.mark.skipif(os.environ.get('HARNESS_DOCKER_TESTS') != '1', reason='opt-in Colima external-Skill isolation probe')
def test_real_external_skill_container_isolation(client):
    from backend.sandbox import docker, docker_command
    import subprocess

    built = subprocess.run(docker_command() + [
        'build', '-f', 'sandbox/external-skill.Dockerfile', '-t', 'harnessagent-external-skill:0.1', 'sandbox',
    ], cwd=str(external_skills.ROOT), capture_output=True, timeout=120, check=False)
    assert built.returncode == 0, built.stderr.decode()
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
        'host_visible': os.path.exists('/Users/weberzhao'),
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
