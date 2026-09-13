"""Pure, no-model control-plane reducer for the proposed Plan/Replan contract."""

from __future__ import annotations


EXIT_ORDER = ("continue", "finish", "clarify", "retry", "replan", "interrupt")
RELIABILITY_STATES = {"verified", "dirty", "invalid"}
REPLAN_ADMISSION_CAPABILITIES = ("state.checkpoint", "state.restore", "control.cancel", "output.structured")
REPLAN_TRANSITIONS = {
    ("proposed", "try"): "trying",
    ("trying", "try_passed"): "awaiting_confirmation",
    ("trying", "try_failed"): "rejected",
    ("awaiting_confirmation", "confirm"): "confirmed",
    ("awaiting_confirmation", "reject"): "rejected",
}
TERMINAL_REPLAN_STATES = {"confirmed", "rejected", "cancelled", "expired"}


def _require_keys(value, keys):
    if not isinstance(value, dict) or any(key not in value for key in keys):
        raise ValueError("control snapshot is incomplete")


def _capability_supported(value):
    return value is True or (isinstance(value, dict) and value.get("supported") is True)


def assess_replan_adapter(descriptor):
    """Classify an Adapter descriptor without probing, executing, or registering it."""
    _require_keys(descriptor, ("adapter_id", "adapter_version", "engine", "capabilities"))
    capabilities = descriptor["capabilities"]
    if not isinstance(capabilities, dict):
        raise ValueError("adapter capabilities must be an object")
    missing = [name for name in REPLAN_ADMISSION_CAPABILITIES if not _capability_supported(capabilities.get(name))]
    return {
        "adapter_id": descriptor["adapter_id"],
        "adapter_version": descriptor["adapter_version"],
        "engine": descriptor["engine"],
        "status": "eligible_for_runtime_probe" if not missing else "ineligible",
        "missing_capabilities": missing,
        "runtime_enabled": False,
    }


def eligible_actions(snapshot):
    """Return registered actions that satisfy hard gates, plus audit reason codes."""
    _require_keys(snapshot, (
        "candidate_actions", "registered_action_ids", "satisfied_preconditions",
        "effective_permissions", "remaining_budget",
    ))
    registered = set(snapshot["registered_action_ids"])
    satisfied = set(snapshot["satisfied_preconditions"])
    permissions = set(snapshot["effective_permissions"])
    remaining = snapshot["remaining_budget"]
    if not isinstance(remaining, int) or remaining < 0:
        raise ValueError("remaining_budget must be a non-negative integer")
    eligible, rejected = [], []
    for action in snapshot["candidate_actions"]:
        _require_keys(action, ("id", "hard_preconditions", "required_permissions", "cost_units"))
        reasons = []
        if action["id"] not in registered:
            reasons.append("ACTION_UNREGISTERED")
        if not set(action["hard_preconditions"]).issubset(satisfied):
            reasons.append("HARD_PRECONDITION_UNMET")
        if not set(action["required_permissions"]).issubset(permissions):
            reasons.append("PERMISSION_DENIED")
        if not isinstance(action["cost_units"], int) or action["cost_units"] < 0 or action["cost_units"] > remaining:
            reasons.append("BUDGET_EXCEEDED")
        if reasons:
            rejected.append({"action_id": action["id"], "reason_codes": reasons})
        else:
            eligible.append(action)
    return {"eligible": eligible, "rejected": rejected}


def validate_plan_graph(nodes):
    """Reject duplicate, dangling or cyclic node dependencies before a plan can be tried."""
    if not isinstance(nodes, list) or not nodes:
        raise ValueError("plan nodes are required")
    by_id = {}
    for node in nodes:
        _require_keys(node, ("id", "depends_on"))
        if node["id"] in by_id:
            raise ValueError("plan contains duplicate node IDs")
        by_id[node["id"]] = tuple(node["depends_on"])
    if any(dependency not in by_id for dependencies in by_id.values() for dependency in dependencies):
        raise ValueError("plan dependency is unknown")
    visiting, visited = set(), set()

    def visit(identifier):
        if identifier in visiting:
            raise ValueError("plan dependencies contain a cycle")
        if identifier in visited:
            return
        visiting.add(identifier)
        for dependency in by_id[identifier]:
            visit(dependency)
        visiting.remove(identifier)
        visited.add(identifier)

    for identifier in by_id:
        visit(identifier)
    return True


def choose_exit(snapshot):
    """Choose one of six legal exits without making a tool or model call."""
    _require_keys(snapshot, (
        "success_criteria_met", "evidence_gate_passed", "retry_eligible", "replan_eligible",
        "core_gap_unresolvable", "candidate_actions", "registered_action_ids",
        "satisfied_preconditions", "effective_permissions", "remaining_budget",
    ))
    if snapshot["success_criteria_met"] and snapshot["evidence_gate_passed"]:
        return {"exit": "finish", "chosen_action_id": None, "reason_codes": ["SUCCESS_AND_EVIDENCE_GATE_PASSED"]}
    if snapshot["retry_eligible"]:
        return {"exit": "retry", "chosen_action_id": None, "reason_codes": ["TRANSIENT_IDEMPOTENT_FAILURE"]}
    if snapshot["replan_eligible"]:
        return {"exit": "replan", "chosen_action_id": None, "reason_codes": ["PATH_OR_ASSUMPTION_INVALID"]}
    candidates = eligible_actions(snapshot)
    if candidates["eligible"]:
        selected = candidates["eligible"][0]
        return {"exit": "continue", "chosen_action_id": selected["id"], "reason_codes": ["REGISTERED_ACTION_ELIGIBLE"]}
    if snapshot["core_gap_unresolvable"]:
        return {"exit": "clarify", "chosen_action_id": None, "reason_codes": ["CORE_GAP_UNRESOLVABLE"]}
    return {"exit": "interrupt", "chosen_action_id": None, "reason_codes": ["NO_SAFE_ELIGIBLE_ACTION"]}


def propagate_reliability(records):
    """Propagate invalid/dirty dependencies; no derived record may become more trusted."""
    if not isinstance(records, list) or not records:
        raise ValueError("reliability records are required")
    by_id = {}
    for record in records:
        _require_keys(record, ("id", "reliability", "depends_on"))
        if record["id"] in by_id or record["reliability"] not in RELIABILITY_STATES:
            raise ValueError("invalid reliability record")
        by_id[record["id"]] = {"reliability": record["reliability"], "depends_on": tuple(record["depends_on"])}
    for record in by_id.values():
        if any(dependency not in by_id for dependency in record["depends_on"]):
            raise ValueError("reliability dependency is unknown")
    visiting, visited = set(), set()

    def visit(identifier):
        if identifier in visiting:
            raise ValueError("reliability dependencies contain a cycle")
        if identifier in visited:
            return
        visiting.add(identifier)
        for dependency in by_id[identifier]["depends_on"]:
            visit(dependency)
        visiting.remove(identifier)
        visited.add(identifier)

    for identifier in by_id:
        visit(identifier)
    for _ in range(len(by_id)):
        changed = False
        for record in by_id.values():
            dependencies = [by_id[dependency]["reliability"] for dependency in record["depends_on"]]
            derived = "invalid" if "invalid" in dependencies else ("dirty" if "dirty" in dependencies else record["reliability"])
            if derived != record["reliability"]:
                record["reliability"] = derived
                changed = True
        if not changed:
            return {identifier: record["reliability"] for identifier, record in by_id.items()}
    raise ValueError("reliability propagation did not converge")


def validate_claim_evidence(claim, evidence_by_id):
    """Enforce cross-record Evidence state before a Claim can be treated as supported."""
    _require_keys(claim, ("kind", "status", "reliability", "supporting_evidence_ids", "contradicting_evidence_ids"))
    all_ids = set(claim["supporting_evidence_ids"]) | set(claim["contradicting_evidence_ids"])
    if any(identifier not in evidence_by_id for identifier in all_ids):
        raise ValueError("claim evidence reference is unknown")
    if claim["kind"] == "fact" and not claim["supporting_evidence_ids"]:
        raise ValueError("fact claim requires supporting evidence")
    if claim["status"] == "supported":
        if (claim["reliability"] != "verified" or not claim["supporting_evidence_ids"]
                or claim["contradicting_evidence_ids"]):
            raise ValueError("supported claim has invalid evidence state")
        for identifier in claim["supporting_evidence_ids"]:
            evidence = evidence_by_id[identifier]
            if evidence.get("reliability") != "verified" or evidence.get("validation_status") != "passed":
                raise ValueError("supported claim depends on unverified evidence")
    if claim["status"] == "contradicted":
        if claim["reliability"] != "invalid" or not claim["contradicting_evidence_ids"]:
            raise ValueError("contradicted claim has invalid evidence state")
    if claim["status"] == "retracted" and claim["reliability"] != "invalid":
        raise ValueError("retracted claim has invalid reliability")
    return True


def evaluate_try(context, candidate_plan_nodes=None):
    """Validate a proposed Replan before confirmation; it has no execution side effects."""
    _require_keys(context, (
        "checkpoint_reliability", "adapter_capabilities", "candidate_plan_digest_present",
        "candidate_permissions", "origin_permissions", "candidate_budget", "remaining_budget",
        "compatibility_digest_matches",
    ))
    failures = []
    if candidate_plan_nodes is not None:
        try:
            validate_plan_graph(candidate_plan_nodes)
        except ValueError:
            failures.append("PLAN_GRAPH_INVALID")
    if context["checkpoint_reliability"] != "verified":
        failures.append("CHECKPOINT_NOT_VERIFIED")
    capabilities = context["adapter_capabilities"]
    if not all(_capability_supported(capabilities.get(name)) for name in ("state.checkpoint", "state.restore", "control.cancel")):
        failures.append("ADAPTER_RESTORE_UNSUPPORTED")
    if not context["candidate_plan_digest_present"]:
        failures.append("CANDIDATE_PLAN_UNBOUND")
    if not set(context["candidate_permissions"]).issubset(set(context["origin_permissions"])):
        failures.append("PERMISSION_EXPANSION")
    if context["candidate_budget"] > context["remaining_budget"]:
        failures.append("BUDGET_EXPANSION")
    if not context["compatibility_digest_matches"]:
        failures.append("COMPATIBILITY_MISMATCH")
    return {"passed": not failures, "failure_codes": failures}


def transition_replan(status, event):
    """Implement Try/Confirm/Cancel state transitions for a sidecar ReplanAttempt."""
    if status not in {"proposed", "trying", "awaiting_confirmation", *TERMINAL_REPLAN_STATES}:
        raise ValueError("unknown replan status")
    if event == "cancel" and status not in TERMINAL_REPLAN_STATES:
        return "cancelled"
    if event == "expire" and status not in TERMINAL_REPLAN_STATES:
        return "expired"
    target = REPLAN_TRANSITIONS.get((status, event))
    if target is None:
        raise ValueError("illegal replan transition")
    return target
