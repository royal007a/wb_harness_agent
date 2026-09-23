"""Fail-closed, non-secret admission state for a future Pi L3 probe."""
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
SCHEMA = json.loads((ROOT / 'specs/v1/pi-admission.schema.json').read_text())
ADMISSION_STATE = ROOT / 'harness/pi-admission.json'
CREDENTIAL_REF = re.compile(r'^keychain://harnessagent/[A-Za-z0-9._-]{1,96}$')
SECRET_LIKE = re.compile(r'(?:sk-[A-Za-z0-9_-]{8,}|bearer\s+[A-Za-z0-9._-]{8,}|api[_-]?key\s*[=:])', re.IGNORECASE)


def _digest(value: dict[str, Any]) -> str:
    return sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def _contains_secret(value: Any) -> bool:
    if isinstance(value, str):
        return bool(SECRET_LIKE.search(value))
    if isinstance(value, dict):
        return any(_contains_secret(item) for item in value.values())
    if isinstance(value, list):
        return any(_contains_secret(item) for item in value)
    return False


def _host(endpoint: str) -> str:
    parsed = urlparse(endpoint)
    if parsed.scheme not in {'http', 'https'} or not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise ValueError('endpoint must be a credential-free HTTP(S) URL without query or fragment')
    return parsed.hostname.lower()


def _credential_ref(value: str | None) -> bool:
    return value is None or bool(CREDENTIAL_REF.fullmatch(value))


def validate(value: dict[str, Any]) -> dict[str, Any]:
    errors = list(Draft202012Validator(SCHEMA, format_checker=FormatChecker()).iter_errors(value))
    if errors:
        raise ValueError('; '.join(error.message for error in errors))
    if _contains_secret(value):
        raise ValueError('admission profile must not contain a secret-like value')
    sources = value['sources']
    if value['status'] == 'not_admitted':
        if value['admission_enabled'] or value['model_calls'] or value['external_calls']:
            raise ValueError('not_admitted must be disabled with zero calls')
        if any(value[name] is not None for name in ('provider', 'model', 'budget', 'public_pdf', 'admission_evidence')):
            raise ValueError('not_admitted must not contain activation configuration')
        if sources['allowed_domains'] or any(item['endpoint'] or item['credential_ref'] for item in (sources['search'], sources['financial'])):
            raise ValueError('not_admitted must not contain external source configuration')
        if any(value['operators'].values()) or not value['blockers']:
            raise ValueError('not_admitted requires blockers and unassigned operators')
        return value
    if not value['admission_enabled'] or value['blockers'] or value['model_calls'] or value['external_calls']:
        raise ValueError('approved_for_l3_probe must be enabled, unblocked and zero calls in the profile')
    if not all(value[name] is not None for name in ('provider', 'model', 'budget', 'public_pdf', 'admission_evidence')):
        raise ValueError('approved_for_l3_probe requires provider/model/budget/PDF/evidence')
    if not all(value['operators'].values()):
        raise ValueError('approved_for_l3_probe requires cancel and rollback owners')
    if sources['allowed_domains'] != sorted(sources['allowed_domains']) or not sources['allowed_domains']:
        raise ValueError('approved_for_l3_probe requires sorted exact domains')
    for connector in (sources['search'], sources['financial']):
        if not _credential_ref(connector['credential_ref']):
            raise ValueError('credential references must use keychain://harnessagent/<name>')
        if not connector['endpoint'] or _host(connector['endpoint']) not in sources['allowed_domains']:
            raise ValueError('every enabled endpoint host must be in allowed_domains')
    return value


def load(path: Path | None = None) -> dict[str, Any]:
    try:
        return validate(json.loads((ADMISSION_STATE if path is None else path).read_text()))
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        raise Problem('PI_ADMISSION_INVALID', 'Pi L3 准入档案无效，保持关闭。', 409) from exc


def runtime_status(path: Path | None = None) -> dict[str, Any]:
    try:
        value = load(path)
    except Problem:
        return {'schema_version': 'pi-admission@1', 'status': 'invalid_not_admitted',
                'admission_enabled': False, 'model_calls': 0, 'external_calls': 0,
                'blocker_count': 1, 'admission_digest': None, 'error': 'admission_profile_invalid'}
    return {'schema_version': value['schema_version'], 'status': value['status'],
            'admission_enabled': value['admission_enabled'], 'model_calls': value['model_calls'],
            'external_calls': value['external_calls'], 'blocker_count': len(value['blockers']),
            'admission_digest': _digest(value), 'error': None}


def require_approved(path: Path | None = None) -> dict[str, Any]:
    value = load(path)
    if value['status'] != 'approved_for_l3_probe' or not value['admission_enabled']:
        raise Problem('PI_ADMISSION_NOT_APPROVED', 'Pi L3 准入尚未批准，未启动真实 Provider、Keychain 或网络。', 409)
    return value


__all__ = ['load', 'require_approved', 'runtime_status', 'validate']
