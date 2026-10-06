"""One credential-shape pattern for every local input boundary (HA-0093).

Five modules used to carry their own copy; two of them (agent_runtime, agent_lab)
silently lacked ``password``, so a DSH document containing ``password=...`` was
accepted while Team metadata rejected it. Keep this the only definition.
"""
from __future__ import annotations

import re

CREDENTIAL_SHAPE = re.compile(
    r'(?:\b(?:api[_ -]?key|client[_ -]?secret|access[_ -]?token|refresh[_ -]?token|password)\s*[:=]'
    r'|\bsk-[A-Za-z0-9_-]{10,}|\bAKIA[0-9A-Z]{16}\b)', re.I)
