"""Opt-in HTTP observation, not assertion/branch coverage or acceptance evidence.

Only instrument Starlette's in-process TestClient. Never intercept live HTTP or
persist concrete paths, parameters, headers or bodies.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import subprocess
import threading

import pytest
from starlette.routing import compile_path
from starlette.testclient import _TestClientTransport

from harness.interface_inventory import ROOT, build_inventory, source_hashes


def safe_test_id(nodeid):
    """Pytest auto-generated parameter IDs can contain entire request bodies."""
    if not nodeid:
        return '<outside_test>'
    base, marker, parameters = nodeid.partition('[')
    if marker:
        return base + '[case_sha256=' + hashlib.sha256(parameters.encode()).hexdigest() + ']'
    return base


class Recorder:
    def __init__(self, rows):
        self.rows = rows
        self.matchers = [(row, compile_path(row['path'])[0]) for row in rows]
        self.requests = Counter()
        self.reports = defaultdict(dict)
        self.current = None
        self.unmatched = 0
        self.lock = threading.Lock()

    def observe(self, nodeid, method, path, status):
        # Prefer exact routes to parameter routes, mirroring static route intent.
        matches = [row for row, regex in self.matchers if row['method'] == method and regex.fullmatch(path)]
        with self.lock:
            if not matches:
                self.unmatched += 1
                return
            row = min(matches, key=lambda value: ('{' in value['path'], -len(value['path'])))
            self.requests[(row['id'], safe_test_id(nodeid), status)] += 1

    def result(self):
        routes = []
        for row in self.rows:
            observations = []
            for (ident, nodeid, status), count in sorted(self.requests.items()):
                if ident != row['id']:
                    continue
                phases = self.reports[nodeid]
                passed = phases.get('call') == 'passed' and all(value == 'passed' for value in phases.values())
                observations.append({'test': nodeid, 'http_status': status, 'count': count,
                                     'test_passed': passed, 'test_phases': dict(phases)})
            routes.append({'id': row['id'], 'feature': row['feature'],
                           'observation': 'observed' if observations else 'not_observed',
                           'acceptance': 'not_determined_by_observer', 'tests': observations})
        return {'version': 'http-observations@1', 'routes': routes,
                'unmatched_request_count': self.unmatched,
                'summary': {'total': len(routes), 'observed': sum(bool(row['tests']) for row in routes),
                            'not_observed': sum(not row['tests'] for row in routes)},
                'not_evidence': ['Route matching is not handler/branch/assertion coverage.',
                                 '2xx does not prove business success, SSE completion or real external calls.',
                                 'Includes mocked transports and middleware rejections; review tests separately.']}


def pytest_addoption(parser):
    parser.addoption('--interface-evidence', help='Write sanitized TestClient route observations as JSON')


def pytest_configure(config):
    if not config.getoption('--interface-evidence'):
        return
    recorder = Recorder(build_inventory()['routes'])
    config._interface_recorder = recorder
    original = _TestClientTransport.handle_request
    config._interface_original_transport = original

    def handle_request(transport, request):
        nodeid = recorder.current
        response = original(transport, request)
        recorder.observe(nodeid, request.method, request.url.path, response.status_code)
        return response

    _TestClientTransport.handle_request = handle_request
    config._interface_initial_hashes = source_hashes()


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_protocol(item, nextitem):
    recorder = getattr(item.config, '_interface_recorder', None)
    if recorder:
        recorder.current = item.nodeid
    try:
        yield
    finally:
        if recorder:
            recorder.current = None


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item, call):
    result = yield
    report = result.get_result()
    recorder = getattr(item.config, '_interface_recorder', None)
    if recorder:
        recorder.reports[safe_test_id(item.nodeid)][report.when] = report.outcome


def pytest_sessionfinish(session, exitstatus):
    recorder = getattr(session.config, '_interface_recorder', None)
    if not recorder:
        return
    result = recorder.result()
    hashes = source_hashes()
    head = subprocess.run(['git', 'rev-parse', 'HEAD'], cwd=ROOT, capture_output=True, text=True, check=True).stdout.strip()
    dirty = subprocess.run(['git', 'status', '--porcelain'], cwd=ROOT, capture_output=True, text=True, check=True).stdout
    result.update({'finished_at': datetime.now(timezone.utc).isoformat(), 'git_head': head,
                   'working_tree_dirty': bool(dirty), 'pytest_exitstatus': int(exitstatus),
                   'source_sha256': hashes,
                   'sources_unchanged_during_run': hashes == session.config._interface_initial_hashes,
                   'docker_tests_requested': os.environ.get('HARNESS_DOCKER_TESTS') == '1'})
    target = Path(session.config.getoption('--interface-evidence'))
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
    print('\nHTTP observations (not acceptance): ' + json.dumps(result['summary']))


def pytest_unconfigure(config):
    if hasattr(config, '_interface_original_transport'):
        _TestClientTransport.handle_request = config._interface_original_transport
