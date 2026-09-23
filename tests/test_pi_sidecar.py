from pathlib import Path

import pytest

from adapters.pi_sidecar import PiSidecarClient


PI_ROOT = Path(__file__).parents[1] / 'pi-adapter'


@pytest.mark.skipif(not (PI_ROOT / 'node_modules').is_dir(), reason='run npm ci in pi-adapter first')
def test_python_sidecar_client_maps_offline_contract_events():
    with PiSidecarClient() as client:
        health = client.health()
        assert health['runtime_enabled'] is False
        started = client.start(run_id='run_py_sidecar_1', resource_ref='contract-fixture-1')
        assert started['mode'] == 'faux_offline'
        events = client.drain_until_done('run_py_sidecar_1')
        assert any(event['platform_type'] == 'tool.call.requested' for event in events)
        assert any(event['platform_type'] == 'tool.call.completed' for event in events)
        assert events[-1]['platform_type'] == 'run.result.proposed'
        replay = client.stream(run_id='run_py_sidecar_1')
        assert replay['done'] is True and len(replay['events']) >= len(events)


@pytest.mark.skipif(not (PI_ROOT / 'node_modules').is_dir(), reason='run npm ci in pi-adapter first')
def test_python_sidecar_client_is_fail_closed_for_real_model():
    # The client only sends the offline model contract; a production caller
    # must not silently substitute a real Provider through this path.
    with PiSidecarClient() as client:
        assert client.health()['external_calls'] == 0
