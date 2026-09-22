"""Shared local control-plane metadata safety checks for Team objects."""
from __future__ import annotations

import re

from .analysis import Problem


SENSITIVE_INPUT = re.compile(
    r'(?:\b(?:api[_ -]?key|client[_ -]?secret|access[_ -]?token|refresh[_ -]?token|password)\s*[:=]'
    r'|\bsk-[A-Za-z0-9_-]{10,}|\bAKIA[0-9A-Z]{16}\b)', re.I)


def reject_sensitive(value):
    """Never retain credential-shaped content in collaboration metadata."""
    if isinstance(value, str):
        if SENSITIVE_INPUT.search(value):
            raise Problem('SENSITIVE_INPUT_REJECTED', 'Team 协作记录不接收或保存凭证样式内容。', 422)
    elif isinstance(value, list):
        for item in value:
            reject_sensitive(item)
    elif isinstance(value, dict):
        for item in value.values():
            reject_sensitive(item)
