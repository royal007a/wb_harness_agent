"""Opt-in real VM tests. Never execute the embedded Python on the host."""
import os
import threading

import pytest

from backend.analysis import Problem
from backend.sandbox import DockerSandbox, docker

pytestmark = pytest.mark.skipif(os.environ.get('HARNESS_DOCKER_TESTS') != '1', reason='opt-in Colima VM probe')
RAW = b'region,revenue\nEast,2\nWest,3\nEast,5\n'


def absent(ident):
    result = docker(['container', 'ls', '-aq', '--no-trunc', '--filter', 'id=' + ident])
    assert result.returncode == 0 and not result.stdout.strip()


def test_profile_and_state():
    with DockerSandbox(RAW) as box:
        ident = box.container_id
        config = box.inspect()
        host = config['HostConfig']
        assert config['Config']['User'] == '65532:65532'
        assert host['NetworkMode'] == 'none' and host['ReadonlyRootfs']
        assert host['Memory'] == host['MemorySwap'] == 256 * 1024 * 1024
        assert host['NanoCpus'] == 500000000 and host['PidsLimit'] == 32
        assert host['CapDrop'] == ['ALL'] and 'no-new-privileges=true' in host['SecurityOpt']
        assert [(m['Destination'], m['RW']) for m in config['Mounts'] if m['Type'] == 'bind'] == [('/inputs', False)]
        first = box.execute("import csv; rows = list(csv.DictReader(open('/inputs/data.csv'))); print(len(rows))")
        assert first['logs'].strip() == '3' and first['error'] is None
        second = box.execute("final_answer(sum(float(r['revenue']) for r in rows))")
        assert second['is_final_answer'] and second['output'] == 10
    absent(ident)
    box.cleanup()


@pytest.mark.parametrize('path', ['/inputs/data.csv', '/etc/probe-write'])
def test_readonly_files(path):
    with DockerSandbox(RAW) as box:
        result = box.execute(f"open({path!r}, 'w').write('forbidden')")
        assert result['error'] and not result['is_final_answer']


def test_no_network_host_socket_or_secrets(monkeypatch):
    monkeypatch.setenv('HARNESS_PROBE_SECRET', 'sentinel-not-a-real-secret')
    with DockerSandbox(RAW) as box:
        result = box.execute("""import os, socket
assert os.getuid() == 65532
assert not os.path.exists('/Users/weberzhao')
assert not os.path.exists('/var/run/docker.sock')
assert not {'HARNESS_PROBE_SECRET', 'ANTHROPIC_API_KEY', 'OPENAI_API_KEY', 'HF_TOKEN'} & set(os.environ)
# The pinned official Python image contains a public GPG_KEY fingerprint.
assert set(os.environ) <= {'HOME','HOSTNAME','PATH','LANG','GPG_KEY','PYTHON_SHA256','PYTHON_VERSION','PYTHONDONTWRITEBYTECODE','PYTHONUNBUFFERED'}
sock = socket.socket(); sock.settimeout(0.5)
try:
    sock.connect(('1.1.1.1', 443))
except OSError:
    final_answer({'network_denied': True})
raise AssertionError('network escape')""")
        assert result['error'] is None and result['output'] == {'network_denied': True}


@pytest.mark.parametrize('code,reason', [
    ('while True: pass', 'SANDBOX_TIMEOUT'),
    ("import os; os.write(1, b'x' * 200000)", 'SANDBOX_OUTPUT_LIMIT'),
    ("import os; os.write(1, b'not-json\\n')", 'SANDBOX_PROTOCOL_ERROR'),
])
def test_fatal_errors_cleanup(code, reason):
    with DockerSandbox(RAW, step_timeout=1) as box:
        ident = box.container_id
        with pytest.raises(Problem) as exc:
            box.execute(code)
        assert exc.value.code == reason
        assert box.container_id is None
    absent(ident)


def test_cancel_running_cleanup():
    cancel = threading.Event()
    def check():
        if cancel.is_set():
            raise Problem('CANCELLED', 'probe cancellation')
    with DockerSandbox(RAW, check=check) as box:
        ident = box.container_id
        timer = threading.Timer(.3, cancel.set)
        timer.start()
        try:
            with pytest.raises(Problem) as exc:
                box.execute('while True: pass')
            assert exc.value.code == 'CANCELLED'
        finally:
            timer.cancel()
    absent(ident)


def test_sdk_multi_step_and_error_recovery():
    from adapters.smolagents_probe import run_probe
    result = run_probe(RAW, [
        "raise ValueError('deliberate recoverable error')",
        "import csv; rows=list(csv.DictReader(open('/inputs/data.csv'))); print(list(rows[0]))",
        "final_answer({'East': sum(float(r['revenue']) for r in rows if r['region']=='East'), 'West': 3})",
    ])
    assert result['mode'] == 'scripted_probe' and result['real_model'] is False
    assert result['sdk_calls'] == 3 and result['model_calls'] == 0
    assert result['output'] == {'East': 7, 'West': 3}
    assert result['events'][-1]['type'] == 'sandbox.cleaned'


def test_sdk_budget_no_extra_model_fallback():
    from adapters.smolagents_probe import run_probe
    with pytest.raises(Problem) as exc:
        run_probe(RAW, ['print(1)'], max_calls=1)
    assert exc.value.code == 'BUDGET_EXCEEDED'


def test_sdk_timeout_is_fatal():
    from adapters.smolagents_probe import run_probe
    with pytest.raises(Problem) as exc:
        run_probe(RAW, ['while True: pass', 'final_answer(42)'], step_timeout=.5)
    assert exc.value.code == 'SANDBOX_TIMEOUT'
