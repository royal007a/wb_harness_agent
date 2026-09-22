---
name: industry-analysis
description: Use for a time-bounded industry news and trend brief based on approved search and fetch evidence. Keep source dates and URLs explicit and do not turn missing search results into a market conclusion.
version: 1.0.0
---

# Industry evidence brief

Use only `mcp__research_sources__web_search` and `mcp__research_sources__web_fetch`. Do not use built-in browser, shell, file, edit, generic MCP, or memory tools.

1. Search only for the requested industry and time range. Retrieve a small, diverse candidate set rather than repeatedly searching the same wording.
2. Fetch a result only when its URL is already present in search evidence. Preserve publication date as reported; retrieval time is not publication time.
3. Group statements into sourced facts, plausible but unverified signals, and gaps. Every factual bullet must include its `source_id`.
4. Return `Coverage`, `Dated findings`, `Conflicts / gaps`, and `Source IDs`. Do not fabricate recency, traffic, market share, or causal effects.
5. Do not make investment, regulatory, or price predictions. A sparse or unavailable result means the topic is unassessed.
