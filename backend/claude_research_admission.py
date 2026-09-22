"""Fail-closed, non-secret admission state for a Native Claude L3 probe."""
from __future__ import annotations

from hashlib import sha256
import json
from pathlib import Path
import re
from typing import Any
from urllib.parse import urlparse

from jsonschema import Draft202012Validator, FormatChecker

from .analysis import Problem


ROOT = Path(__file__).resolve().parents[1]
SCHEMA = json.loads((ROOT / 'specs/v1/claude-research-admission.schema.json').read_text())
ADMISSION_STATE = ROOT / 'harness/claude-research-admission.json'
CREDENTIAL_REF = re.compile(r'^keychain://harnessagent/[A-Za-z0-9._-]{1,96}$')
SECRET_LIKE = re.compile(r'(?:sk-[A-Za-z0-9_-]{8,}|bearer\\s+[A-Za-z0-9._-]{8,}|api[_-]?key\\s*[=:])', re.IGNORECASE)


def is_credential_ref(value: str | None) -> bool:
    return isinstance(value, str) and bool(CREDENTIAL_REF.fullmatch(value))


def _digest(value: dict[str, Any]) -> str:
    return sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def _host(endpoint: str) -> str:
    parsed = urlparse(endpoint)
    if parsed.scheme != 'https' or not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise ValueError('endpoint must be a credential-free HTTPS URL without query or fragment')
    return parsed.hostname.lower()


def _contains_secret(value: Any) -> bool:
    if isinstance(value, str):
        return bool(SECRET_LIKE.search(value))
    if isinstance(value, dict):
        return any(_contains_secret(entry) for entry in value.values())
    if isinstance(value, list):
        return any(_contains_secret(entry) for entry in value)
    return False


def validate(value: dict[str, Any]) -> dict[str, Any]:
    errors = list(Draft202012Validator(SCHEMA, format_checker=FormatChecker()).iter_errors(value))
    if errors:
        raise ValueError('; '.join(error.message for error in errors))
    if _contains_secret(value):
        raise ValueError('admission profile must not contain a secret-like value')
    status = value['status']
    sources = value['sources']
    connectors = (sources['search'], sources['financial'])
    if status == 'not_admitted':
        if value['admission_enabled'] or value['model_calls'] or value['external_calls']:
            raise ValueError('not_admitted must be disabled with zero calls')
        if any(value[name] is not None for name in ('provider', 'model', 'budget', 'public_pdf', 'admission_evidence')):
            raise ValueError('not_admitted must not contain an activation configuration or evidence')
        if sources['allowed_domains'] or any(item['endpoint'] or item['credential_ref'] for item in connectors):
            raise ValueError('not_admitted must not contain source endpoints or credential references')
        if any(value['operators'].values()) or not value['blockers']:
            raise ValueError('not_admitted requires unresolved blockers and no assigned operators')
        return value
    if not value['admission_enabled'] or value['blockers']:
        raise ValueError('approved_for_l3_probe requires enabled admission and no blockers')
    if value['model_calls'] or value['external_calls']:
        raise ValueError('an admission profile itself must not claim model or external calls')
    if not all(value[name] is not None for name in ('provider', 'model', 'budget', 'public_pdf', 'admission_evidence')):
        raise ValueError('approved_for_l3_probe requires provider, model, budget, Public PDF and evidence')
    if not all(value['operators'].values()):
        raise ValueError('approved_for_l3_probe requires cancellation and rollback owners')
    if not sources['allowed_domains'] or any(not item['endpoint'] for item in connectors):
        raise ValueError('approved_for_l3_probe requires exact domains and both endpoints')
    if sources['allowed_domains'] != sorted(sources['allowed_domains']):
        raise ValueError('approved_for_l3_probe requires allowed_domains in deterministic sorted order')
    for connector in connectors:
        if connector['credential_ref'] is not None and not is_credential_ref(connector['credential_ref']):
            raise ValueError('credential references must use keychain://harnessagent/<name>')
        if _host(connector['endpoint']) not in sources['allowed_domains']:
            raise ValueError('every endpoint host must be in allowed_domains')
    return value


def load(path: Path | None = None) -> dict[str, Any]:
    path = ADMISSION_STATE if path is None else path
    try:
        return validate(json.loads(path.read_text()))
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        raise Problem('CLAUDE_RESEARCH_ADMISSION_INVALID', '原生投研准入档案无效，保持关闭。', 409) from exc


def runtime_status(path: Path | None = None) -> dict[str, Any]:
    try:
        value = load(path)
    except Problem:
        return {
            'schema_version': 'claude-research-admission@1', 'status': 'invalid_not_admitted',
            'admission_enabled': False, 'model_calls': 0, 'external_calls': 0,
            'blocker_count': 1, 'admission_digest': None, 'error': 'admission_profile_invalid',
        }
    return {
        'schema_version': value['schema_version'], 'status': value['status'],
        'admission_enabled': value['admission_enabled'], 'model_calls': value['model_calls'],
        'external_calls': value['external_calls'], 'blocker_count': len(value['blockers']),
        'admission_digest': _digest(value), 'error': None,
    }


def require_approved(path: Path | None = None) -> dict[str, Any]:
    value = load(path)
    if value['status'] != 'approved_for_l3_probe' or not value['admission_enabled']:
        raise Problem('CLAUDE_RESEARCH_ADMISSION_NOT_APPROVED', '原生投研 L3 准入档案尚未批准，未启动 SDK、CLI、Keychain 或网络。', 409)
    return value


def assert_runtime_binding(admission: dict[str, Any], *, model: str | None, cli_path: str,
                           allowed_domains: tuple[str, ...], max_cost_minor: int,
                           max_turns: int, timeout_seconds: int) -> None:
    provider, budget, sources = admission['provider'], admission['budget'], admission['sources']
    if (provider['cli_path'] != cli_path or admission['model'] != model or
            tuple(sources['allowed_domains']) != tuple(allowed_domains) or
            max_cost_minor > budget['max_cost_minor'] or max_turns > budget['max_turns'] or
            timeout_seconds > budget['timeout_seconds']):
        raise Problem('CLAUDE_RESEARCH_ADMISSION_MISMATCH', '原生投研运行配置超出已批准的 L3 准入档案。', 409)


def assert_source_binding(admission: dict[str, Any], policy) -> None:
    sources = admission['sources']
    expected = (sources['search'], sources['financial'])
    actual = ((policy.search_endpoint, policy.search_credential_ref),
              (policy.financial_endpoint, policy.financial_credential_ref))
    if tuple(policy.allowed_domains) != tuple(sources['allowed_domains']) or any(
            item['endpoint'] != endpoint or item['credential_ref'] != credential_ref
            for item, (endpoint, credential_ref) in zip(expected, actual, strict=True)):
        raise Problem('CLAUDE_RESEARCH_ADMISSION_MISMATCH', '资料源配置与已批准的 L3 准入档案不一致。', 409)


def assert_public_pdf_binding(admission: dict[str, Any], resource: dict[str, Any]) -> None:
    approved = admission['public_pdf']
    if (resource.get('data_class') != 'Public' or resource.get('name') != approved['name'] or
            resource.get('sha256') != approved['sha256']):
        raise Problem('CLAUDE_RESEARCH_PUBLIC_PDF_MISMATCH', '已登记 PDF 与 L3 准入档案不一致。', 409)
