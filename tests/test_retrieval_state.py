import copy
import hashlib
import json
import re
import unicodedata
from pathlib import Path

from jsonschema import Draft202012Validator

from harness.retrieval_state_validation import valid_retrieval_state


ROOT = Path(__file__).resolve().parents[1]
SCHEMA = json.loads((ROOT / "specs/v1/retrieval-state.schema.json").read_text())


def query_key(terms, entity_ids=(), filters=(), source_ids=(), methods=("keyword",), direction="support"):
    terms = re.findall(r"[\w]+", unicodedata.normalize("NFKC", " ".join(terms)).casefold(), flags=re.UNICODE)
    canonical = {
        "query_terms": sorted(set(terms)), "entity_ids": sorted(set(entity_ids)),
        "filters": sorted(filters), "source_ids": sorted(source_ids),
        "methods": sorted(methods), "direction": direction,
    }
    return hashlib.sha256(json.dumps(canonical, ensure_ascii=False, separators=(",", ":")).encode()).hexdigest()


def candidate(eid="e1"):
    return {"evidence_id": eid, "source_ref": "source:1", "summary": "derived evidence", "summary_kind": "derived_redacted", "rank": 1, "novelty": 1.0, "gap_ids": ["gap:1"]}


def valid_state():
    key = query_key(["支付", "故障"], ["system:payment"], [("as_of", "2026-09-24")])
    return {
        "schema_version": "retrieval-state@1", "session_id": "rs_1", "max_rounds": 3,
        "source_trust_mode": "unavailable",
        "policy": {"max_rounds": 3, "dup_threshold": 0.8, "near_duplicate_jaccard": 0.8, "min_new_evidence": 2, "no_progress_rounds": 2, "min_evidence_per_claim": 1},
        "rounds": [{"round": 1, "query": "支付 故障", "query_delta": "新增支付系统实体与日期过滤", "query_key": key, "source_ids": ["memory:m1"], "methods": ["keyword", "temporal"], "candidate_evidence": [candidate()], "new_evidence_ids": ["e1"], "confirmed_fact_ids": ["fact:1"], "open_gap_ids": ["gap:1"], "continue_reason": "关键 Gap 尚未覆盖", "next_round_goal": "查找风控依赖证据", "attempt": 1, "rerun_reason": None, "budget": {"elapsed_ms": 10, "token_count": 0, "tool_calls": 1, "cost_minor": 0}, "duplicate_rate": 0, "coverage_delta": 0.5}],
        "stop_reason": None,
    }


def validator():
    Draft202012Validator.check_schema(SCHEMA)
    return Draft202012Validator(SCHEMA)


def test_valid_instance_and_query_key_vectors():
    state = valid_state()
    assert valid_retrieval_state(state, validator())
    assert query_key(["支付", "故障"]) == query_key(["故障", "支付"])
    assert query_key(["A" ]) == query_key(["a"])


def test_five_negative_instances_are_rejected():
    cases = []
    x = copy.deepcopy(valid_state()); x["rounds"][0]["methods"] = ["semantic"]; cases.append(x)
    x = copy.deepcopy(valid_state()); x["rounds"][0]["attempt"] = 2; cases.append(x)
    x = copy.deepcopy(valid_state()); x["stop_reason"] = None; x["rounds"][0]["continue_reason"] = None; cases.append(x)
    x = copy.deepcopy(valid_state()); x["max_rounds"] = 0; cases.append(x)
    x = copy.deepcopy(valid_state()); x["rounds"][0]["round"] = 2; cases.append(x)
    assert all(not valid_retrieval_state(case, validator()) for case in cases)
