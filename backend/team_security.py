"""Shared local control-plane metadata safety checks for Team objects."""
from __future__ import annotations


from .analysis import Problem
from .sensitive_patterns import CREDENTIAL_SHAPE


SENSITIVE_INPUT = CREDENTIAL_SHAPE  # single shared definition (backend/sensitive_patterns.py)


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
