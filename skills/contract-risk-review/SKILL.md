---
name: contract-risk-review
description: Review a pi-contract-pipeline preview and produce a cited, human-gated risk candidate; use after deterministic PDF preview, never as legal advice or as a substitute for source evidence.
---

# Contract Risk Review Skill

This Skill consumes the structured preview from
`POST /api/local/pi-contract-pipeline/preview`. It does not read arbitrary host
paths, call a provider, browse the web, or invent clauses that are absent from
the preview.

## Workflow

1. Validate `schema_version`, `resource_id`, `source_sha256`, chunk hashes and
   `security` before review.
2. Run `scripts/review_preview.py` for deterministic baseline findings. Keep the
   output as a candidate artifact, not a legal conclusion.
3. For model-backed review (not enabled in the current deployment), inspect
   each chunk independently, preserve chunk index/hash as evidence, then run a
   separate cross-chunk pass for definitions, liability caps, termination and
   dispute clauses.
4. Every high-risk finding must reference the current `resource_id` and chunk
   hash. Missing or sensitive evidence changes the result to `needs_human`.
5. Return the candidate through the existing Handoff + Gate flow. Never mark a
   contract review delivered solely because parsing or retry succeeded.

## Output boundary

Use `status=needs_human` for baseline candidates. Include `risk_level`,
`evidence_refs`, `recommendation`, and `method`; do not include raw sensitive
matches or claim enforceability. Human review remains responsible for legal and
commercial decisions.
