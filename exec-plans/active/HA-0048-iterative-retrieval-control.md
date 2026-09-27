# HA-0048：迭代式检索控制契约

## Objective

把 ADR-0041 的设计变成可机器校验、可评测的 Retrieval State 契约；只实现本地确定性状态/规则，不启用 embedding、外部网络或模型化 Query Expansion。

## Scope

- 固化 `specs/v1/retrieval-state.schema.json` 与默认阈值。
- 定义 query_key、重跑 attempt、字符 3-gram Jaccard 近似重复、信息增益与排序公式。
- 明确 source trust 当前不可用，并以 `source_trust_mode=unavailable` 固化。
- 为后续实现补齐合成评测和 stop reason 证据。

## Non-goals

- 不接入 embedding、RRF、reranker、外部资料、Provider 或真实 Agentic RAG。
- 不把检索结果作为权威事实，不做自动冲突裁决。

## Acceptance

1. Schema 解析通过，`tasks.json`、计划和 Evidence 路径可追踪。
2. 每轮具备 query/query_delta/query_key、候选与新增 evidence、事实、Gap、继续/下一轮目标、attempt/重跑原因、实际预算和 stop reason。
3. 默认 `max_rounds=3`；有效新增少于 2 条视为无进展，连续两轮停止；重复率达到 0.8 停止；关键 Claim 每个至少需要 1 条允许来源证据。
4. 重复判定、novelty、排序和修改成本均有确定性公式与固定平局规则。
5. `harness/verify.sh` 与 retrieval schema/评测检查通过；review 结论归档。

## Evidence

`harness/evidence/HA-0048/acceptance.md`

