---
name: risk-review
description: Use for an evidence-limited A-share risk review. Identify coverage and gaps from approved financial, report, search, and fetch sources; never convert missing evidence into a claim of no ST, delisting, litigation, or governance risk.
version: 1.0.0
---

# Evidence-limited risk review

Use only `mcp__research_sources__financial_data`, `mcp__research_sources__pdf_extract`, `mcp__research_sources__web_search`, and `mcp__research_sources__web_fetch`. Do not use built-in browser, shell, file, edit, generic MCP, or memory tools.

1. Define the covered risk categories before drawing conclusions: financial pressure, audit/reporting, regulatory/litigation, listing status, governance, and market information gaps.
2. Use the financial API/PDF for reported facts, and search/fetch only for approved public-source evidence. Attach the returned `source_id` to every factual observation.
3. For each category label status exactly as `observed`, `conflicting`, or `unassessed`. `unassessed` is never `no risk`.
4. Return `Coverage matrix`, `Observed evidence`, `Conflicts`, `Unassessed items`, and `Source IDs`. Do not pronounce ST/退市 status or give a trading recommendation unless an authoritative, dated source explicitly supports the narrowly worded fact.
5. Do not infer future events, probabilities, or safety from absent information.
