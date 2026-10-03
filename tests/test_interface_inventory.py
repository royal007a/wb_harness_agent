import json

from harness.interface_inventory import DIRECTORY, ROOT, build_inventory, feature_for, features, render
from harness.pytest_interface_evidence import Recorder, safe_test_id


def test_all_registered_routes_and_features_match_versioned_spec():
    actual = build_inventory()
    assert actual == json.loads((DIRECTORY / 'interfaces.json').read_text())
    assert render(actual) == (DIRECTORY / 'INTERFACES.md').read_text()
    ids = [row['id'] for row in actual['routes']]
    assert len(ids) == len(set(ids))
    assert 'GET /api/local/connectors/baidu-netdisk/callback' in ids
    assert 'GET /openapi.json' in ids
    assert 'HEAD /static/{path:path}' in ids
    feature_ids = [row['id'] for row in features()]
    assert len(feature_ids) == len(set(feature_ids))
    for row in features():
        assert row['boundary'] and row['checks'] and row['specs']
        for path in row['specs'] + row['tests']:
            assert (ROOT / path).is_file(), path


def test_unknown_api_group_is_not_hidden_by_page_fallback():
    import pytest
    with pytest.raises(ValueError, match='Unclassified API'):
        feature_for('/api/local/unreviewed-new-feature')


def test_framework_inventory_is_independent_of_venv_install_location(monkeypatch):
    import harness.interface_inventory as inventory
    original = inventory.inspect.getsourcefile
    snapshots = []
    for location in (ROOT / '.venv/lib/python3.14/site-packages/fastapi/applications.py',
                     '/opt/isolated-test-env/lib/python3.12/site-packages/fastapi/applications.py'):
        monkeypatch.setattr(inventory.inspect, 'getsourcefile',
            lambda endpoint: str(location) if endpoint.__name__ == 'openapi' else original(endpoint))
        snapshots.append(build_inventory())
    assert snapshots[0] == snapshots[1]
    assert all(row['source'] == 'framework' for row in snapshots[0]['routes'] if row['path'] == '/openapi.json')


def test_observer_redacts_ids_and_never_claims_acceptance():
    recorder = Recorder(build_inventory()['routes'])
    test = 'tests/test_example.py::test_case'
    recorder.observe(test, 'GET', '/api/v1/runs/private-personal-id', 200)
    recorder.observe(test, 'GET', '/unregistered/private-path', 404)
    recorder.reports[test] = {'setup': 'passed', 'call': 'passed', 'teardown': 'failed'}
    report = recorder.result()
    raw = json.dumps(report)
    assert 'private-personal-id' not in raw and 'private-path' not in raw
    hit = next(row for row in report['routes'] if row['id'] == 'GET /api/v1/runs/{run_id}')
    assert hit['observation'] == 'observed'
    assert hit['acceptance'] == 'not_determined_by_observer'
    assert hit['tests'][0]['test_passed'] is False
    assert report['unmatched_request_count'] == 1
    assert report['summary']['not_observed'] > 0


def test_observer_does_not_misclassify_static_runtime_route_as_id():
    recorder = Recorder(build_inventory()['routes'])
    recorder.observe('case', 'GET', '/api/local/research-native/runtime', 200)
    observed = [row['id'] for row in recorder.result()['routes'] if row['tests']]
    assert observed == ['GET /api/local/research-native/runtime']


def test_observer_does_not_copy_parameter_payloads_from_test_ids():
    nodeid = 'tests/test_example.py::test_case[private-fixture-content]'
    recorder = Recorder(build_inventory()['routes'])
    recorder.observe(nodeid, 'GET', '/api/v1/health', 200)
    recorder.reports[safe_test_id(nodeid)] = {'setup': 'passed', 'call': 'passed', 'teardown': 'passed'}
    result = recorder.result()
    assert 'private-fixture-content' not in json.dumps(result)
    hit = next(row for row in result['routes'] if row['id'] == 'GET /api/v1/health')
    assert hit['tests'][0]['test_passed'] is True
    assert '[case_sha256=' in hit['tests'][0]['test']
