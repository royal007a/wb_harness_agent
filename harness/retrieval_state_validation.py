"""Deterministic checks that JSON Schema intentionally cannot express."""
from __future__ import annotations

from collections.abc import Mapping


def validate_retrieval_state(value: Mapping) -> list[str]:
    errors: list[str] = []
    rounds = value.get("rounds", [])
    max_rounds = value.get("max_rounds")
    policy = value.get("policy", {})
    if isinstance(policy, Mapping) and policy.get("max_rounds") != max_rounds:
        errors.append("policy_max_rounds_mismatch")
    if isinstance(max_rounds, int) and len(rounds) > max_rounds:
        errors.append("rounds_exceed_max_rounds")
    numbers = [item.get("round") for item in rounds if isinstance(item, Mapping)]
    if numbers != list(range(1, len(numbers) + 1)):
        errors.append("rounds_must_be_contiguous_and_unique")
    seen_keys: set[str] = set()
    for item in rounds:
        if not isinstance(item, Mapping):
            continue
        key = item.get("query_key")
        attempt = item.get("attempt", 1)
        if attempt == 1 and key in seen_keys:
            errors.append("duplicate_query_key_requires_rerun_attempt")
        if isinstance(key, str):
            seen_keys.add(key)
    return errors


def valid_retrieval_state(value: Mapping, schema_validator) -> bool:
    return not list(schema_validator.iter_errors(value)) and not validate_retrieval_state(value)
