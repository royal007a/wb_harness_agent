import json
from pathlib import Path

from jsonschema import Draft202012Validator

import pytest

from backend.adaptive_retrieval import build_parent_child_chunks, expand_parent_context, retrieval_control, should_stop_minimal, slot_progress, validate_adaptive_chunks, weighted_rrf


def test_parent_child_prefers_structure_and_preserves_lineage():
    result = build_parent_child_chunks("第1条 付款\n甲方应在验收后付款。乙方应提供发票。\n\n第2条 交付\n乙方应在十日内交付。", max_child_chars=400)
    assert result["parents"] and result["children"]
    parent_ids = {item["id"] for item in result["parents"]}
    assert all(item["parent_id"] in parent_ids for item in result["children"])
    validate_adaptive_chunks(result)
    assert {item["strategy"] for item in result["children"]} <= {"structural", "hard_limit"}
    assert expand_parent_context(result, [result["children"][0]["id"]])
    schema = json.loads(Path("specs/v1/adaptive-chunk.schema.json").read_text())
    assert not list(Draft202012Validator(schema).iter_errors(result))


def test_weighted_rrf_and_parent_evidence_are_deterministic():
    rows = [
        {"child_id": "c1", "parent_id": "p1", "route": "keyword", "rank": 1},
        {"child_id": "c1", "parent_id": "p1", "route": "graph", "rank": 2},
        {"child_id": "c2", "parent_id": "p2", "route": "keyword", "rank": 2},
    ]
    fused = weighted_rrf(rows, {"keyword": 1.0, "graph": 0.5})
    assert fused[0]["child_id"] == "c1" and fused[0]["parent_score"] > fused[-1]["parent_score"]
    with pytest.raises(ValueError):
        weighted_rrf([{"child_id": "x", "parent_id": "p", "route": "semantic", "rank": 1}])


def test_parent_limit_is_real_and_ids_are_content_addressed():
    text = "第1条 总则\n" + ("很长内容。" * 4000)
    result = build_parent_child_chunks(text, max_child_chars=400, parent_max_chars=1000)
    assert all(item["char_count"] <= 1000 for item in result["parents"])
    second = build_parent_child_chunks("第0条 前置\n说明。\n" + text, max_child_chars=400, parent_max_chars=1000)
    assert {item["text_sha256"]: item["id"] for item in result["parents"]}.keys() <= {item["text_sha256"] for item in second["parents"]}


def test_slots_drive_minimal_stop_not_iteration_count():
    evidence = [{"id": "e1", "slots": ["A"]}, {"id": "e2", "slots": ["B"]}]
    assert slot_progress(["A", "B", "C"], evidence)["missing"] == ["C"]
    assert not should_stop_minimal(["A", "B", "C"], evidence)
    assert should_stop_minimal(["A", "B"], evidence)
    assert not should_stop_minimal(["A", "B"], evidence, ["conflict"])
    assert retrieval_control(["A"], evidence, budget={"token_count": 0})["reason"] == "budget_exhausted"
    assert retrieval_control(["A", "B", "C"], evidence, rounds_without_progress=1)["retry"] is True
    assert retrieval_control(["A", "B", "C"], evidence, rounds_without_progress=2)["reason"] == "no_progress"
