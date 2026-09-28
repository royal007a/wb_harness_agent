"""Deterministic adaptive chunking and retrieval primitives.

This module deliberately stays inside the admitted local retrieval boundary:
no embeddings, network calls, model calls, or implicit budget increases.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import re
from typing import Iterable


HEADING = re.compile(r"^(?:第[一二三四五六七八九十百零]+章|第\d+条|\d+[.)、])(?:\s*.*)?$")
SENTENCE = re.compile(r"(?<=[。！？!?；;])\s*")


def _sha(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _units(text: str) -> list[tuple[str, str]]:
    """Return structural units, preferring headings, paragraphs, then sentences."""
    units: list[tuple[str, str]] = []
    for paragraph in re.split(r"\n\s*\n", text.replace("\r", "\n")):
        paragraph = paragraph.strip()
        if not paragraph:
            continue
        lines = [line.strip() for line in paragraph.splitlines() if line.strip()]
        if len(lines) > 1 and HEADING.match(lines[0]):
            units.append((lines[0], "\n".join(lines)))
            continue
        sentences = [item.strip() for item in SENTENCE.split(paragraph) if item.strip()]
        units.extend(("", item) for item in sentences or [paragraph])
    return units


@dataclass(frozen=True)
class AdaptiveChunk:
    id: str
    parent_id: str
    index: int
    heading: str
    structural_path: tuple[str, ...]
    text: str
    strategy: str

    def as_dict(self) -> dict:
        return {
            "id": self.id,
            "parent_id": self.parent_id,
            "index": self.index,
            "heading": self.heading,
            "structural_path": list(self.structural_path),
            "char_count": len(self.text),
            "text_sha256": _sha(self.text),
            "strategy": self.strategy,
        }


def build_parent_child_chunks(text: str, max_child_chars: int = 1800, parent_max_chars: int = 9000) -> dict:
    """Compile structural parents and retrieval-sized children deterministically.

    A parent is a section/paragraph context; children are sentence/paragraph
    evidence units. Hard splitting is only the final fallback for an oversized
    atomic unit, so callers do not rely on one fixed chunk size.
    """
    if not isinstance(text, str) or not text.strip():
        raise ValueError("text must be non-empty")
    if not 400 <= max_child_chars <= 8000 or not 1000 <= parent_max_chars <= 24000:
        raise ValueError("chunk limits out of range")
    parents: list[dict] = []
    children: list[AdaptiveChunk] = []
    parent_no = 0
    current_heading = ""
    current: list[str] = []

    def flush() -> None:
        nonlocal parent_no, current
        if not current:
            return
        parent_text = "\n".join(current).strip()
        parent_id = f"parent-{parent_no:04d}-{_sha(parent_text)[:12]}"
        path = (current_heading,) if current_heading else (f"section-{parent_no + 1}",)
        parents.append({"id": parent_id, "heading": current_heading, "text_sha256": _sha(parent_text), "char_count": len(parent_text), "structural_path": list(path)})
        child_parts: list[str] = []
        for _, unit in _units(parent_text):
            if child_parts and len("\n".join(child_parts)) + len(unit) + 1 > max_child_chars:
                _append_children(children, parent_id, path, child_parts, len(children), "structural")
                child_parts = []
            if len(unit) > max_child_chars:
                if child_parts:
                    _append_children(children, parent_id, path, child_parts, len(children), "structural")
                    child_parts = []
                for start in range(0, len(unit), max_child_chars):
                    _append_children(children, parent_id, path, [unit[start:start + max_child_chars]], len(children), "hard_limit")
            else:
                child_parts.append(unit)
        if child_parts:
            _append_children(children, parent_id, path, child_parts, len(children), "structural")
        parent_no += 1
        current = []

    for line in text.replace("\r", "").splitlines():
        line = line.strip()
        if not line:
            continue
        if HEADING.match(line) and current:
            flush()
            current_heading = line
        elif HEADING.match(line):
            current_heading = line
        current.append(line)
        if sum(len(item) + 1 for item in current) >= parent_max_chars:
            flush()
    flush()
    return {"schema_version": "adaptive-chunk@1", "parents": parents, "children": [item.as_dict() for item in children]}


def _append_children(out: list[AdaptiveChunk], parent_id: str, path: tuple[str, ...], parts: list[str], index: int, strategy: str) -> None:
    value = "\n".join(parts).strip()
    if not value:
        return
    out.append(AdaptiveChunk(f"child-{index:04d}-{_sha(value)[:12]}", parent_id, index, path[-1], path, value, strategy))


def weighted_rrf(candidates: Iterable[dict], route_weights: dict[str, float] | None = None, rrf_k: int = 60, top_k: int = 8) -> list[dict]:
    """Fuse route rankings and promote parents only from observed children."""
    weights = route_weights or {"keyword": 1.0, "temporal": 0.8, "graph": 0.8}
    scores: dict[str, float] = {}
    rows: dict[str, dict] = {}
    for row in candidates:
        cid = row["child_id"]
        route = row["route"]
        rank = int(row["rank"])
        scores[cid] = scores.get(cid, 0.0) + float(weights.get(route, 0.0)) / (rrf_k + rank)
        rows[cid] = dict(row)
    ranked = sorted(scores, key=lambda cid: (-scores[cid], cid))[:top_k]
    return [{**rows[cid], "score": round(scores[cid], 8)} for cid in ranked]


def slot_progress(required_slots: Iterable[str], evidence: Iterable[dict]) -> dict:
    required = list(dict.fromkeys(required_slots))
    filled = {slot for item in evidence for slot in item.get("slots", []) if slot in required}
    return {"required": required, "filled": sorted(filled), "missing": sorted(set(required) - filled), "complete": set(required) <= filled}


def should_stop_minimal(required_slots: Iterable[str], evidence: Iterable[dict], blocking_gaps: Iterable[str] = ()) -> bool:
    progress = slot_progress(required_slots, evidence)
    return progress["complete"] and not set(blocking_gaps)


__all__ = ["AdaptiveChunk", "build_parent_child_chunks", "slot_progress", "should_stop_minimal", "weighted_rrf"]
