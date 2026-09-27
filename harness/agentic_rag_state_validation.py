"""Semantic validation for retrieval-state@2 beyond JSON Schema."""
from collections.abc import Mapping


def validate_agentic_state(value: Mapping) -> list[str]:
    errors: list[str] = []
    policy = value.get("policy", {})
    cache = value.get("cache_policy", {})
    if cache.get("enabled") is not False or cache.get("negative_cache") is not False or cache.get("identity_scope_digest") is not None:
        errors.append("cache_policy_disabled")
    initial = value.get("initial_budget", {})
    remaining = value.get("remaining_budget", {})
    dimensions = ("elapsed_ms", "token_count", "tool_calls", "cost_minor")
    spent = {key: sum(item.get("budget_spent", {}).get(key, 0) for item in value.get("rounds", [])) for key in dimensions}
    for key in spent:
        if remaining.get(key, 0) > initial.get(key, 0) or initial.get(key, 0) - spent[key] != remaining.get(key, 0):
            errors.append("budget_snapshot_does_not_reconcile")
            break
    cumulative = {key: 0 for key in dimensions}
    for item in value.get("rounds", []):
        for key in dimensions:
            cumulative[key] += item.get("budget_spent", {}).get(key, 0)
            expected_remaining = initial.get(key, 0) - cumulative[key]
            if item.get("remaining_budget_after", {}).get(key) != expected_remaining:
                errors.append("remaining_budget_after_does_not_reconcile")
                break
    exhausted = any(remaining.get(key, 0) <= 0 for key in dimensions)
    if exhausted and value.get("stop_reason") != "budget_exhausted":
        errors.append("budget_exhausted_must_hard_stop")
    if value.get("stop_reason") == "budget_exhausted" and not exhausted:
        errors.append("budget_exhausted_without_exhaustion")
    if value.get("initial_budget") != value.get("remaining_budget") and not value.get("rounds"):
        errors.append("budget_without_rounds")
    goals = {g.get("goal_id"): g for g in value.get("goals", []) if isinstance(g, Mapping)}
    if len(goals) != len(value.get("goals", [])):
        errors.append("duplicate_goal_id")
    # Dependency references must exist and be acyclic.
    for goal_id in goals:
        visiting: set[str] = set()
        visited: set[str] = set()
        def visit(node: str) -> None:
            if node in visiting:
                errors.append("goal_dependency_cycle")
                return
            if node in visited or node not in goals:
                if node not in goals:
                    errors.append("goal_dependency_missing")
                return
            visiting.add(node)
            for dep in goals[node].get("depends_on", []): visit(dep)
            visiting.remove(node); visited.add(node)
        visit(goal_id)
    for goal in goals.values():
        deps = [goals.get(dep) for dep in goal.get("depends_on", [])]
        if goal.get("status") in {"active", "completed"} and any(dep is None or dep.get("status") != "completed" for dep in deps):
            errors.append("goal_dependency_not_completed")
        if goal.get("status") == "active" and goal.get("user_confirmation") != "confirmed":
            errors.append("active_goal_without_user_confirmation")
        if goal.get("status") == "completed":
            if goal.get("blocking_gap_ids"):
                errors.append("completed_goal_has_blocking_gap")
            counts = goal.get("evidence_count_by_claim", {})
            if set(counts) != set(goal.get("claims", [])):
                errors.append("completed_goal_claim_coverage_incomplete")
            if any(counts.get(claim, 0) < policy.get("min_evidence_per_claim", 1) for claim in goal.get("claims", [])):
                errors.append("completed_goal_missing_claim_evidence")
    if value.get("stop_reason") == "minimal_target_satisfied" and not any(g.get("status") == "completed" for g in goals.values()):
        errors.append("minimal_target_not_completed")
    tiers = {item.get("tier"): item for item in value.get("strategy_tiers", []) if isinstance(item, Mapping)}
    expected = {1: ("local_keyword", {"keyword"}), 2: ("local_temporal_graph", {"temporal", "graph"}), 3: ("admitted_semantic_or_external", {"semantic", "api"})}
    for tier, (name, allowed) in expected.items():
        item = tiers.get(tier)
        if item and (item.get("id") != name or (tier == 3 and item.get("admitted") is not False)):
            errors.append("strategy_tier_snapshot_invalid")
    for item in value.get("rounds", []):
        if item.get("round") != len([r for r in value.get("rounds", []) if r.get("round", 0) <= item.get("round", 0)]):
            errors.append("rounds_must_be_contiguous_and_unique")
        if item.get("goal_id") not in goals:
            errors.append("round_goal_missing")
        if item.get("strategy_tier") not in tiers:
            errors.append("strategy_tier_not_snapshotted")
        else:
            tier = item["strategy_tier"]; allowed = expected.get(tier, (None, set()))[1]
            if any(method not in allowed for method in item.get("methods", [])):
                errors.append("strategy_method_tier_mismatch")
            if tier == 3 and not tiers[tier].get("admitted"):
                errors.append("unadmitted_strategy_method")
        change = item.get("strategy_change")
        if change and (change.get("from_tier") not in tiers or change.get("to_tier") not in tiers or change.get("to_tier") != item.get("strategy_tier")):
            errors.append("strategy_change_not_snapshotted")
    # Carry forward v1 state invariants.
    rounds = value.get("rounds", [])
    if len(rounds) > policy.get("max_rounds", 0): errors.append("rounds_exceed_max_rounds")
    numbers = [r.get("round") for r in rounds]
    if numbers != list(range(1, len(numbers) + 1)): errors.append("rounds_must_be_contiguous_and_unique")
    seen_keys: set[str] = set()
    for item in rounds:
        if item.get("attempt", 1) == 1 and item.get("query_key") in seen_keys:
            errors.append("duplicate_query_key_requires_rerun_attempt")
        seen_keys.add(item.get("query_key"))
    return errors
