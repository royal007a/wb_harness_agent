"""Read-only capability report: persisted probe evidence is not a live SLA."""
from importlib.metadata import PackageNotFoundError, version
import json

from .sandbox import ROOT, profile_digest

EVIDENCE = ROOT / 'harness/evidence/HA-0007/probe.json'


def readiness():
    try:
        sdk = version('smolagents')
    except PackageNotFoundError:
        sdk = None
    probe = None
    try:
        saved = json.loads(EVIDENCE.read_text())
        current = saved.get('profile_sha256') == profile_digest() and saved.get('smolagents_version') == sdk
        probe = {'status': 'passed_at_probe' if current and saved.get('status') == 'passed' else 'stale_or_failed',
                 'checked_at': saved.get('checked_at'), 'image_id': saved.get('image_id'),
                 'tests': saved.get('tests'), 'real_model': False}
    except (OSError, ValueError):
        probe = {'status': 'not_run', 'real_model': False}
    return {'baseline': 'available', 'smolagents_version': sdk, 'sandbox_probe': probe,
            'research_demo': {'status':'available', 'real_model':False, 'max_children':9, 'max_concurrency':3,
                              'url':'/research', 'execution':'fixed_functions'},
            'model_route_enabled': False,
            'blocking_items': ['approved_model_endpoint_and_credentials', 'live_model_budget_and_cancel_probe',
                               'production_adapter_contract_acceptance'],
            'skill_package': {'name': 'csv-group-analysis', 'status': 'local_script_only', 'auto_installed': False},
            'note': '探针为指定版本的历史证据；不代表容器当前存活、真实模型已接入或生产安全认证。'}
