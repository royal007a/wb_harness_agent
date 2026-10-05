"""One-way persistence projection; never a source for model/aggregate input."""
from __future__ import annotations

import hashlib
import json

from .analysis import Problem


KINDS = frozenset({
    'assistant.text', 'assistant.tool_use', 'assistant.tool_result',
    'sdk.system', 'sdk.result', 'sdk.rate_limit',
    'run.started', 'model.call.started', 'model.message', 'model.delta',
    'tool.call.requested', 'tool.call.progress', 'tool.call.completed',
    'step.completed', 'run.result.proposed',
})


def fingerprint(value):
    raw = json.dumps(value, ensure_ascii=True, sort_keys=True,
                     separators=(',', ':'), allow_nan=False).encode('utf-8')
    return {'sha256': hashlib.sha256(raw).hexdigest(), 'bytes': len(raw)}


def project_runtime_event(kind, payload):
    if not isinstance(kind, str) or kind not in KINDS or not isinstance(payload, dict):
        raise Problem('RUNTIME_EVENT_INVALID', '运行时观察事件不满足元数据投影契约。', 409)
    try:
        summary = fingerprint(payload)
        result = {'schema_version': 'runtime-event-metadata@1', 'kind': kind,
                  'payload_sha256': summary['sha256'], 'payload_bytes': summary['bytes']}
        if type(payload.get('is_error')) is bool:
            result['is_error'] = payload['is_error']
        if kind == 'sdk.result':
            errors = payload.get('errors', [])
            if not isinstance(errors, list):
                raise ValueError('invalid errors')
            result['error_count'] = len(errors)
            result['errors'] = [{'category': 'sdk_error', **fingerprint(error)} for error in errors[:64]]
        return result
    except (TypeError, ValueError, RecursionError) as exc:
        raise Problem('RUNTIME_EVENT_INVALID', '运行时观察事件无法投影为元数据。', 409) from exc
