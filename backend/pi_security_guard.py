"""Metadata-only security guard for the Pi contract pipeline.

The guard evaluates an intended action; it never executes tools, opens files,
contacts a network, or invokes a model.  Unknown capabilities fail closed.
"""
from __future__ import annotations

from urllib.parse import urlparse
import re
import json
from pathlib import Path
from jsonschema import Draft202012Validator

from .analysis import Problem

_ROOT = Path(__file__).resolve().parents[1]
_SCHEMA = json.loads((_ROOT / "specs/v1/pi-security-guard.schema.json").read_text())


_SENSITIVE = (
    ("身份证号", re.compile(r"\d{6}(?:19|20)\d{2}(?:0[1-9]|1[0-2])(?:0[1-9]|[12]\d|3[01])\d{3}[\dXx]")),
    ("手机号", re.compile(r"(?<!\d)1[3-9]\d{9}(?!\d)")),
    ("银行卡号", re.compile(r"(?<!\d)\d{16,19}(?!\d)")),
    ("邮箱", re.compile(r"(?i)[\w.-]+@[\w.-]+\.\w+")),
    ("凭据", re.compile(r"(?i)(?:api[_-]?key|secret|token|password)\s*[:=]")),
)
_FORBIDDEN_SEGMENTS = {".ssh", ".env", ".aws", ".git", ".gnupg", ".pi-agent", "node_modules"}


def _text(action: dict) -> str:
    values = []
    for key in ("content", "url", "path"):
        value = action.get(key)
        if isinstance(value, str):
            values.append(value)
    return "\n".join(values)


def _deny(action: dict, reasons: list[str]) -> dict:
    return {
        "schema_version": "pi-security-guard@1",
        "decision": "deny",
        "phase": action.get("phase", "unknown"),
        "tool": action.get("tool"),
        "reasons": reasons or ["GUARD_DENY_UNSPECIFIED"],
        "model_calls": 0,
        "external_calls": 0,
    }


def evaluate(action: dict, policy: dict) -> dict:
    """Return an allow/deny decision without performing the requested action."""
    if not isinstance(action, dict) or not isinstance(policy, dict):
        raise Problem("VALIDATION_ERROR", "action 和 policy 必须为 JSON 对象。", 422)
    request = {"action": action, "policy": policy}
    contract = {"$ref": "#/$defs/request", "$defs": _SCHEMA["$defs"]}
    if list(Draft202012Validator(contract).iter_errors(request)):
        raise Problem("VALIDATION_ERROR", "安全护栏请求不满足机器契约。", 422)
    phase = action.get("phase")
    if phase not in {"tool_call", "tool_result", "context", "provider_request"}:
        return _deny(action, ["GUARD_UNKNOWN_PHASE"])
    reasons: list[str] = []
    allowed_tools = policy.get("allowed_tools", [])
    tool = action.get("tool")
    if phase in {"tool_call", "tool_result"}:
        if not isinstance(tool, str) or tool not in allowed_tools:
            reasons.append("GUARD_TOOL_NOT_ALLOWED")
    text = _text(action)
    if text:
        for name, pattern in _SENSITIVE:
            if pattern.search(text):
                reasons.append("GUARD_SENSITIVE_CONTENT")
                break
    path = action.get("path")
    if path is not None:
        if not isinstance(path, str) or path.startswith(("/", "\\")) or ".." in path.replace("\\", "/").split("/"):
            reasons.append("GUARD_PATH_OUTSIDE_WORKSPACE")
        elif any(segment.lower() in _FORBIDDEN_SEGMENTS for segment in path.replace("\\", "/").split("/")):
            reasons.append("GUARD_FORBIDDEN_PATH")
    url = action.get("url")
    if url is not None:
        parsed = urlparse(url) if isinstance(url, str) else None
        domains = policy.get("allowed_domains", [])
        if (not parsed or parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password
                or parsed.query or parsed.fragment or parsed.hostname.lower() not in domains):
            reasons.append("GUARD_DOMAIN_NOT_ALLOWED")
    for amount_key, limit_key, reason in (("estimated_tokens", "max_input_tokens", "GUARD_TOKEN_BUDGET_EXCEEDED"),
                                           ("estimated_cost_minor", "max_cost_minor", "GUARD_COST_BUDGET_EXCEEDED")):
        amount = action.get(amount_key, 0)
        limit = policy.get(limit_key, 0)
        if not isinstance(amount, int) or amount < 0 or not isinstance(limit, int) or limit < 0 or amount > limit:
            reasons.append(reason)
    if phase == "provider_request" and policy.get("provider_admitted") is not True:
        reasons.append("GUARD_PROVIDER_NOT_ADMITTED")
    if reasons:
        return _deny(action, sorted(set(reasons)))
    return {
        "schema_version": "pi-security-guard@1", "decision": "allow", "phase": phase,
        "tool": tool, "reasons": [], "model_calls": 0, "external_calls": 0,
    }


class PiSecurityGuard:
    """Idempotent HTTP facade; this object has no execution authority."""

    def __init__(self, service):
        self.service = service

    def check(self, body: dict, key: str | None):
        if not isinstance(body, dict) or set(body) != {"action", "policy"}:
            raise Problem("VALIDATION_ERROR", "请求必须只包含 action 和 policy。", 422)
        return self.service.idempotent("pi-security-guard:check", key, body, lambda _db: evaluate(body["action"], body["policy"]))


__all__ = ["PiSecurityGuard", "evaluate"]
