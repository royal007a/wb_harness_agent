import copy
import json
from pathlib import Path
from jsonschema import Draft202012Validator
from harness.agentic_rag_state_validation import validate_agentic_state

ROOT = Path(__file__).resolve().parents[1]
SCHEMA = json.loads((ROOT / "specs/v1/retrieval-state-v2.schema.json").read_text())


def budget(cost=100):
    return {"elapsed_ms": cost, "token_count": cost, "tool_calls": cost, "cost_minor": cost}


def valid_state():
    return {
        "schema_version": "retrieval-state@2", "session_id": "rs2_1",
        "policy": {"max_rounds": 3, "dup_threshold": 0.8, "near_duplicate_jaccard": 0.8, "min_new_evidence": 2, "no_progress_rounds": 2, "min_evidence_per_claim": 1},
        "strategy_tiers": [{"tier": 1, "id": "local_keyword", "admitted": True, "admission_ref": "local@1"}, {"tier": 2, "id": "local_temporal_graph", "admitted": True, "admission_ref": "local@1"}, {"tier": 3, "id": "admitted_semantic_or_external", "admitted": False, "admission_ref": None}],
        "goals": [
            {"goal_id": "goal:select-project", "title": "选最适合放简历的项目", "independent_value": True, "claims": ["project_choice"], "depends_on": [], "status": "completed", "user_confirmation": "confirmed", "blocking_gap_ids": [], "evidence_count_by_claim": {"project_choice": 1}},
            {"goal_id": "goal:optimize-project", "title": "优化选中的项目", "independent_value": True, "claims": ["optimization_plan"], "depends_on": ["goal:select-project"], "status": "active", "user_confirmation": "confirmed", "blocking_gap_ids": ["gap:optimization"], "evidence_count_by_claim": {"optimization_plan": 0}},
            {"goal_id": "goal:interview-questions", "title": "生成面试题", "independent_value": True, "claims": ["question_set"], "depends_on": ["goal:optimize-project"], "status": "planned", "user_confirmation": "pending", "blocking_gap_ids": [], "evidence_count_by_claim": {"question_set": 0}}
        ],
        "rounds": [{"round": 1, "goal_id": "goal:select-project", "query_key": "a" * 64, "methods": ["keyword"], "strategy_tier": 1, "candidate_evidence_ids": ["e1"], "new_evidence_ids": ["e1"], "open_gap_ids": ["gap:optimization"], "budget_spent": budget(10), "remaining_budget_after": budget(90), "strategy_change": None, "continue_reason": "下一目标需用户确认", "next_round_goal": "goal:optimize-project", "attempt": 1, "rerun_reason": None}],
        "initial_budget": budget(100), "remaining_budget": budget(90), "cache_policy": {"enabled": False, "negative_cache": False, "ttl_seconds": 300, "identity_scope_digest": None, "invalidation_mode": "evidence_reverse_index"}, "stop_reason": None
    }


def validator():
    Draft202012Validator.check_schema(SCHEMA)
    return Draft202012Validator(SCHEMA)


def test_three_goal_fixture_is_valid():
    state = valid_state(); assert not list(validator().iter_errors(state)); assert not validate_agentic_state(state)


def test_negative_fixtures_are_rejected_individually():
    cases = []
    x = copy.deepcopy(valid_state()); x["strategy_tiers"][2]["admitted"] = True; x["strategy_tiers"][2]["admission_ref"] = None; cases.append(x)
    x = copy.deepcopy(valid_state()); x["rounds"][0]["methods"] = ["semantic"]; x["rounds"][0]["strategy_tier"] = 3; cases.append(x)
    x = copy.deepcopy(valid_state()); x["cache_policy"]["enabled"] = True; cases.append(x)
    x = copy.deepcopy(valid_state()); x["goals"][0]["status"] = "completed"; x["goals"][0]["blocking_gap_ids"] = ["gap:x"]; cases.append(x)
    x = copy.deepcopy(valid_state()); x["remaining_budget"] = budget(0); x["stop_reason"] = None; cases.append(x)
    for case in cases:
        assert list(validator().iter_errors(case)) or validate_agentic_state(case)
