"""Deterministic adaptive parent/child retrieval primitives (local only)."""
from __future__ import annotations
import hashlib
import re
from dataclasses import dataclass
from typing import Iterable

ALLOWED_ROUTES = frozenset({"keyword", "temporal", "graph"})
HEADING = re.compile(r"^(?P<mark>(?:#{1,6}\s+|第[一二三四五六七八九十百零]+章|第\d+条|[一二三四五六七八九十]+、|\d+[.)、]\s*))(?P<title>.*)$")
SENTENCE = re.compile(r"(?<=[。！？!?；;])\s*")

def _sha(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()

def _heading_level(mark: str) -> int:
    return len(mark.strip()) if mark.startswith("#") else 1

@dataclass(frozen=True)
class AdaptiveChunk:
    id: str
    parent_id: str
    index: int
    heading: str
    structural_path: tuple[str, ...]
    text: str
    start: int
    end: int
    strategy: str
    def as_dict(self) -> dict:
        return {"id": self.id, "parent_id": self.parent_id, "index": self.index, "heading": self.heading, "structural_path": list(self.structural_path), "text": self.text, "start": self.start, "end": self.end, "char_count": len(self.text), "text_sha256": _sha(self.text), "strategy": self.strategy}

def _split_units(text: str, base: int) -> list[tuple[str, int, int, str]]:
    out, cursor = [], 0
    for block in re.split(r"\n\s*\n", text):
        raw = block.strip()
        if not raw:
            cursor += len(block) + 2; continue
        start = text.find(raw, cursor); cursor = start + len(raw)
        lines = [line.strip() for line in raw.splitlines() if line.strip()]
        if len(lines) > 1 and all(line.startswith(("- ", "* ", "|")) or re.match(r"^\\d+[.)、]", line) for line in lines):
            pieces, kind = lines, "list_or_table"
        else:
            pieces, kind = ([item.strip() for item in SENTENCE.split(raw) if item.strip()] or [raw]), "sentence"
        local = start
        for piece in pieces:
            pos = text.find(piece, local, start + len(raw)); out.append((piece, base + pos, base + pos + len(piece), kind)); local = pos + len(piece)
    return out

def _append_child(out: list[AdaptiveChunk], parent_id: str, path: tuple[str, ...], units: list[tuple[str, int, int, str]], strategy: str) -> None:
    value = "\\n".join(item[0] for item in units).strip()
    if not value: return
    start, end = units[0][1], units[-1][2]
    child_id = f"child-{_sha(parent_id + chr(0) + value + chr(0) + str(start))[:16]}"
    out.append(AdaptiveChunk(child_id, parent_id, len(out), path[-1], path, value, start, end, strategy))

def build_parent_child_chunks(text: str, max_child_chars: int = 1800, parent_max_chars: int = 9000) -> dict:
    if not isinstance(text, str) or not text.strip(): raise ValueError("text must be non-empty")
    if not 400 <= max_child_chars <= 8000 or not 1000 <= parent_max_chars <= 24000: raise ValueError("chunk limits out of range")
    lines, parents, children = text.replace("\r", "").splitlines(keepends=True), [], []
    section, section_start, offset, path, levels = [], 0, 0, [], []
    def flush() -> None:
        nonlocal section, section_start
        raw = "".join(section).strip()
        if not raw: section = []; return
        fragments, local = [], 0
        while local < len(raw):
            end = min(local + parent_max_chars, len(raw))
            if end < len(raw):
                boundary = max(raw.rfind("\\n\\n", local, end), raw.rfind("\\n", local, end))
                if boundary > local + parent_max_chars // 2: end = boundary
            fragment = raw[local:end].strip()
            fragments.append((fragment, section_start + local, _sha(raw[:local])))
            local = end
        for fragment, frag_start, prefix_digest in fragments:
            if not fragment: continue
            parent_id, parent_path = f"parent-{_sha(fragment + chr(0) + prefix_digest)[:16]}", tuple(path or ["document"])
            parents.append({"id": parent_id, "heading": parent_path[-1], "text": fragment, "start": frag_start, "end": frag_start + len(fragment), "text_sha256": _sha(fragment), "char_count": len(fragment), "structural_path": list(parent_path)})
            pending: list[tuple[str, int, int, str]] = []
            for unit in _split_units(fragment, frag_start):
                if pending and len("\\n".join(x[0] for x in pending + [unit])) > max_child_chars:
                    _append_child(children, parent_id, parent_path, pending, "structural"); pending = []
                if len(unit[0]) > max_child_chars:
                    if pending: _append_child(children, parent_id, parent_path, pending, "structural"); pending = []
                    for begin in range(0, len(unit[0]), max_child_chars):
                        piece = unit[0][begin:begin + max_child_chars]
                        _append_child(children, parent_id, parent_path, [(piece, unit[1] + begin, unit[1] + begin + len(piece), "hard_limit")], "hard_limit")
                else: pending.append(unit)
            if pending: _append_child(children, parent_id, parent_path, pending, "structural")
        section = []
    for line in lines:
        stripped = line.strip(); match = HEADING.match(stripped)
        if match:
            level = _heading_level(match.group("mark"))
            if section and level <= (levels[-1] if levels else level): flush()
            while levels and level <= levels[-1]: path.pop(); levels.pop()
            path.append(match.group("title").strip() or stripped); levels.append(level)
        if not section: section_start = offset + len(line) - len(line.lstrip())
        section.append(line); offset += len(line)
    flush()
    result = {"schema_version": "adaptive-chunk@1", "parents": parents, "children": [item.as_dict() for item in children], "parent_max_chars": parent_max_chars, "max_child_chars": max_child_chars}
    validate_adaptive_chunks(result); return result

def validate_adaptive_chunks(result: dict) -> None:
    parents, children = result.get("parents", []), result.get("children", [])
    parent_ids = [x.get("id") for x in parents]
    if len(parent_ids) != len(set(parent_ids)): raise ValueError("duplicate parent id")
    if len({x.get("id") for x in children}) != len(children): raise ValueError("duplicate child id")
    if [x.get("index") for x in children] != list(range(len(children))): raise ValueError("child indexes must be contiguous")
    if any(x.get("parent_id") not in parent_ids for x in children): raise ValueError("child references unknown parent")
    if any(not x.get("text") or x.get("char_count") != len(x["text"]) for x in children): raise ValueError("child text/length mismatch")
    limit = int(result.get("parent_max_chars", 24000))
    if any(x.get("char_count", 0) > limit for x in parents): raise ValueError("parent hard limit exceeded")

def weighted_rrf(candidates: Iterable[dict], route_weights: dict[str, float] | None = None, rrf_k: int = 60, top_k: int = 8, per_route_top_k: dict[str, int] | None = None) -> list[dict]:
    weights = route_weights or {"keyword": 1.0, "temporal": 0.8, "graph": 0.8}
    if set(weights) - ALLOWED_ROUTES or any(not isinstance(v, (int, float)) or v < 0 for v in weights.values()): raise ValueError("route is not admitted or weight is invalid")
    caps = per_route_top_k or {route: top_k for route in ALLOWED_ROUTES}
    if set(caps) - ALLOWED_ROUTES or any(int(v) < 1 for v in caps.values()): raise ValueError("per-route topK is invalid")
    scores, rows, route_scores = {}, {}, {}
    for row in candidates:
        route, cid, rank = row.get("route"), row.get("child_id"), int(row["rank"])
        if route not in ALLOWED_ROUTES: raise ValueError(f"route not admitted: {route}")
        if rank < 1 or rank > caps.get(route, top_k): continue
        contribution = float(weights.get(route, 0.0)) / (rrf_k + rank); scores[cid] = scores.get(cid, 0.0) + contribution
        route_scores.setdefault(cid, {})[route] = route_scores.setdefault(cid, {}).get(route, 0.0) + contribution
        rows.setdefault(cid, {"child_id": cid, "parent_id": row["parent_id"]})
    grouped = {}
    for cid, score in scores.items(): grouped.setdefault(rows[cid]["parent_id"], []).append(score)
    parent_scores = {parent: sum(sorted(values, reverse=True)[:3]) / min(3, len(values)) for parent, values in grouped.items()}
    ranked = sorted(scores, key=lambda cid: (-scores[cid], -parent_scores[rows[cid]["parent_id"]], cid))[:top_k]
    return [{**rows[cid], "routes": sorted(route_scores[cid]), "route_scores": route_scores[cid], "score": round(scores[cid], 8), "parent_score": round(parent_scores[rows[cid]["parent_id"]], 8), "policy": {"route_weights": dict(weights), "per_route_top_k": dict(caps)}} for cid in ranked]

def expand_parent_context(index: dict, child_ids: Iterable[str]) -> list[dict]:
    """Expand only parents referenced by selected children, in stable order."""
    wanted = set(child_ids)
    parent_ids = {child["parent_id"] for child in index.get("children", []) if child["id"] in wanted}
    return [parent for parent in index.get("parents", []) if parent["id"] in parent_ids]

def slot_progress(required_slots: Iterable[str], evidence: Iterable[dict]) -> dict:
    required = list(dict.fromkeys(required_slots)); filled = {slot for item in evidence for slot in item.get("slots", []) if slot in required}
    return {"required": required, "filled": sorted(filled), "missing": sorted(set(required) - filled), "complete": set(required) <= filled}

def retrieval_control(required_slots: Iterable[str], evidence: Iterable[dict], blocking_gaps: Iterable[str] = (), rounds_without_progress: int = 0, retry_used: bool = False, budget: dict | None = None) -> dict:
    budget = budget or {}; progress = slot_progress(required_slots, evidence)
    if any(value is not None and value <= 0 for value in budget.values()): return {"stop": True, "reason": "budget_exhausted", "retry": False, "progress": progress}
    if progress["complete"] and not set(blocking_gaps): return {"stop": True, "reason": "minimal_target_satisfied", "retry": False, "progress": progress}
    if rounds_without_progress >= 2: return {"stop": True, "reason": "no_progress", "retry": False, "progress": progress}
    if rounds_without_progress == 1 and not retry_used: return {"stop": False, "reason": "strategy_change", "retry": True, "progress": progress}
    return {"stop": False, "reason": "evidence_gap_open", "retry": False, "progress": progress}

def should_stop_minimal(required_slots: Iterable[str], evidence: Iterable[dict], blocking_gaps: Iterable[str] = ()) -> bool:
    return retrieval_control(required_slots, evidence, blocking_gaps)["reason"] == "minimal_target_satisfied"

__all__ = ["AdaptiveChunk", "build_parent_child_chunks", "expand_parent_context", "retrieval_control", "slot_progress", "should_stop_minimal", "validate_adaptive_chunks", "weighted_rrf"]
