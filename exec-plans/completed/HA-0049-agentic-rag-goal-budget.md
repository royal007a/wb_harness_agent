# HA-0049：Agentic RAG 最小目标与预算控制设计

## Objective

在 HA-0048 Retrieval State 之上定义 Agentic RAG 的目标拆解、策略选择、预算降级、缓存失效和端到端评测契约；只完成设计，不启用外部/语义检索。

## Acceptance

- ADR-0049 与适配文档明确迭代式检索和 Agentic RAG 的边界。
- 最小目标、预算、缓存键/失效和端到端指标可映射到现有 Task/Run/Evidence/Gate。
- 语义/外部能力仍由 ADR-0031 fail-closed；文档不把未实现能力写成 available。

## Non-goals

- 不实现自主 source/tool selection、embedding、RRF、reranker、Provider、网络或缓存运行时。

