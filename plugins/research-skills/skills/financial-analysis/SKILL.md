---
name: financial-analysis
description: Use for a company financial-report analysis that has a registered PDF and/or approved financial API evidence. Extract reported figures with source IDs, preserve period and unit, and mark missing metrics as unassessed.
version: 1.0.0
---

# Financial analysis with evidence

Use only `mcp__research_sources__financial_data`, `mcp__research_sources__pdf_extract`, and (when a source URL was already returned) `mcp__research_sources__web_fetch`. Do not use built-in file, shell, browser, edit, network, or memory tools.

1. Get the target stock code and reporting period from the task. If a period, accounting unit, consolidated/single-company basis, or source is absent, say it is missing; do not infer it.
2. Read the registered report through `pdf_extract` and request only necessary indicators through `financial_data`. Keep the returned `source_id` beside every reported number.
3. Separate reported facts from calculations and qualitative interpretation. State formula, time period and unit for any computed ratio. A number with no source ID is not a factual conclusion.
4. Return a compact Markdown result with: `Facts`, `Calculations`, `Missing / inconsistent evidence`, and `Source IDs`. Do not issue buy/sell/hold advice or predict prices.
5. If sources disagree, preserve both IDs and explain the conflict. If the PDF cannot be extracted, report the error and leave the metric unassessed.
