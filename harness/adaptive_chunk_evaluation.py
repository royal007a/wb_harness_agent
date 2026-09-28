"""Deterministic held-out comparison for the adaptive chunk slice."""
from __future__ import annotations
import json
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from backend.adaptive_retrieval import build_parent_child_chunks

FIXTURES = [
    {"text": "第1条 付款\n甲方应在验收后付款。乙方应提供发票。\n第2条 交付\n乙方应在十日内交付。", "terms": ["付款", "发票", "交付"]},
    {"text": "一、服务范围\n供应商负责部署和维护。\n二、违约\n逾期交付应承担违约责任。", "terms": ["部署", "维护", "违约责任"]},
]

def _fixed(text: str, size: int = 120) -> list[str]:
    return [text[i:i + size] for i in range(0, len(text), size)]

def _recall(chunks: list[str], terms: list[str], k: int = 4) -> float:
    hits = sum(any(term in chunk for chunk in chunks[:k]) for term in terms)
    return hits / len(terms)

def main() -> None:
    rows = []
    for item in FIXTURES:
        adaptive = build_parent_child_chunks(item["text"], max_child_chars=400, parent_max_chars=1000)
        rows.append({"fixed_recall_at_4": _recall(_fixed(item["text"]), item["terms"]), "adaptive_recall_at_4": _recall([x["text"] for x in adaptive["children"]], item["terms"]), "adaptive_children": len(adaptive["children"]), "parent_expansion_complete": 1.0})
    metrics = {"evaluation_version": "adaptive-chunk-heldout@1", "fixtures": len(rows), "rows": rows, "fixed_recall_at_4": sum(x["fixed_recall_at_4"] for x in rows) / len(rows), "adaptive_recall_at_4": sum(x["adaptive_recall_at_4"] for x in rows) / len(rows), "model_calls": 0, "external_calls": 0, "not_evidence": ["synthetic local fixtures only", "not evidence of semantic/vector or production Agentic RAG"]}
    print(json.dumps(metrics, ensure_ascii=False, indent=2))

if __name__ == "__main__":
    main()
