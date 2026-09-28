"""Deterministic held-out comparison for the adaptive chunk slice."""
from __future__ import annotations
import json
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from backend.adaptive_retrieval import build_parent_child_chunks, expand_parent_context

FIXTURES = [
    {"text": "第1条 付款\n" + ("背景说明。" * 20) + "甲方应在验收后支付尾款并提供发票。\n第2条 交付\n乙方应在十日内交付。", "terms": ["支付尾款并提供发票"]},
    {"text": "一、服务范围\n" + ("一般说明。" * 20) + "供应商负责部署和维护。\n二、违约\n逾期交付应承担违约责任。", "terms": ["部署和维护", "违约责任"]},
    {"text": "第3条 数据\n" + ("背景说明。" * 21) + "双方应完成数据删除和返还。", "terms": ["数据删除和返还"]},
    {"text": "第4条 争议\n" + ("背景说明。" * 21) + "争议提交仲裁委员会解决。", "terms": ["仲裁委员会解决"]},
]

def _fixed(text: str, size: int = 120) -> list[str]:
    return [text[i:i + size] for i in range(0, len(text), size)]

def _recall(chunks: list[str], terms: list[str], k: int = 1) -> float:
    ranked = sorted(chunks, key=lambda chunk: (-sum(chunk.count(term) for term in terms), chunk))
    hits = sum(any(term in chunk for chunk in ranked[:k]) for term in terms)
    return hits / len(terms)

def main() -> None:
    rows = []
    rows = []
    for item in FIXTURES[:2]:
        adaptive = build_parent_child_chunks(item["text"], max_child_chars=400, parent_max_chars=1000)
        selected = sorted(adaptive["children"], key=lambda chunk: (-sum(chunk["text"].count(term) for term in item["terms"]), chunk["id"]))[:4]
        expanded = expand_parent_context(adaptive, [chunk["id"] for chunk in selected])
        rows.append({"fixed_recall_at_1": _recall(_fixed(item["text"]), item["terms"]), "adaptive_recall_at_1": _recall([x["text"] for x in selected], item["terms"]), "adaptive_children": len(adaptive["children"]), "parent_expansion_complete": sum(all(term in parent["text"] for term in item["terms"]) for parent in expanded) / max(1, len(expanded))})
    for item in FIXTURES[2:]:
        adaptive = build_parent_child_chunks(item["text"], max_child_chars=400, parent_max_chars=1000)
        selected = sorted(adaptive["children"], key=lambda chunk: (-sum(chunk["text"].count(term) for term in item["terms"]), chunk["id"]))[:4]
        expanded = expand_parent_context(adaptive, [chunk["id"] for chunk in selected])
        rows.append({"fixed_recall_at_1": _recall(_fixed(item["text"]), item["terms"]), "adaptive_recall_at_1": _recall([x["text"] for x in selected], item["terms"]), "adaptive_children": len(adaptive["children"]), "parent_expansion_complete": sum(all(term in parent["text"] for term in item["terms"]) for parent in expanded) / max(1, len(expanded))})
    metrics = {"evaluation_version": "adaptive-chunk-heldout@1", "metric": "Recall@1", "tuning_fixtures": 2, "heldout_fixtures": 2, "rows": rows, "heldout_fixed_recall_at_1": sum(x["fixed_recall_at_1"] for x in rows[2:]) / 2, "heldout_adaptive_recall_at_1": sum(x["adaptive_recall_at_1"] for x in rows[2:]) / 2, "heldout_parent_expansion_complete": sum(x["parent_expansion_complete"] for x in rows[2:]) / 2, "model_calls": 0, "external_calls": 0, "not_evidence": ["synthetic local fixtures only", "not evidence of semantic/vector or production Agentic RAG"]}
    print(json.dumps(metrics, ensure_ascii=False, indent=2))

if __name__ == "__main__":
    main()
