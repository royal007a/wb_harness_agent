"""Semantic validation for retrieval-state@2 beyond JSON Schema."""
from collections.abc import Mapping


def validate_agentic_state(value: Mapping) -> list[str]:
    errors: list[str] = []
    policy = value.get("policy", {})
    initial = value.get("initial_budget", {})
    remaining = value.get("remaining_budget", {})
    spent = {key: sum(item.get("budget_spent", {}).get(key, 0) for item in value.get("rounds", [])) for key in ("elapsed_ms", "token_count", "tool_calls", "cost_minor")}
    for key in spent:
        if remaining.get(key, 0) > initial.get(key, 0) or initial.get(key, 0) - spent[key] != remaining.get(key, 0):
            errors.append("budget_snapshot_does_not_reconcile")
            break
    if value.get("stop_reason") is None and value.get("remaining_budget", {}).get("cost_minor") == 0:
        errors.append("budget_exhausted_must_hard_stop")
    if value.get("initial_budget") != value.get("remaining_budget") and not value.get("rounds"):
        errors.append("budget_without_rounds")
    goals = {g.get("goal_id"): g for g in value.get("goals", []) if isinstance(g, Mapping)}
    for goal in goals.values():
        if goal.get("status") == "completed":
            if goal.get("blocking_gap_ids"):
                errors.append("completed_goal_has_blocking_gap")
            if any(count < policy.get("min_evidence_per_claim", 1) for count in goal.get("evidence_count_by_claim", {}).values()):
                errors.append("completed_goal_missing_claim_evidence")
    for goal in goals.values():
        if any(dep not in goals for dep in goal.get("depends_on", [])):
            errors.append("goal_dependency_missing")
    tiers = {item.get("tier"): item for item in value.get("strategy_tiers", []) if isinstance(item, Mapping)}
    for item in value.get("rounds", []):
        if item.get("strategy_tier") not in tiers:
            errors.append("strategy_tier_not_snapshotted")
        if any(method in {"semantic", "api"} and not tiers.get(item.get("strategy_tier"), {}).get("admitted") for method in item.get("methods", [])):
            errors.append("unadmitted_strategy_method")
    return errors
