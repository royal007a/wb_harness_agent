"""HA-0098: shadow scan of free-template published text (counts only, never blocks).

jikesummary 护栏三明治: new output rules start in shadow mode so false-positive rates
can be measured before anything is blocked or masked. Contract review may legitimately
quote account numbers or phone numbers, so this only records category counts.
"""
from __future__ import annotations

import re

from .dsh_findings import INSTRUCTION_MARKERS
from .sensitive_patterns import CREDENTIAL_SHAPE

SCAN_VERSION = 'dsh-output-scan@1'
CATEGORIES = {
    'credential_shape': CREDENTIAL_SHAPE,
    'instruction_markers': INSTRUCTION_MARKERS,
    'cn_mobile': re.compile(r'(?<!\d)1[3-9]\d{9}(?!\d)'),
    'cn_id_card': re.compile(r'(?<![0-9Xx])\d{17}[0-9Xx](?![0-9Xx])'),
}


def scan(text):
    """Category -> match count. No matched text leaves this function."""
    return {name: len(pattern.findall(text)) for name, pattern in CATEGORIES.items()}
