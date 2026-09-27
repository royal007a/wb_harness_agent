# HA-0049 设计验收证据

状态：completed（设计契约已验收；运行时控制器和真实对照评测另立后续任务）。

- 设计：`docs/decisions/ADR-0049-agentic-rag-goal-budget-cache.md`、`docs/harness/AGENTIC_RAG_ADAPTATION.md`
- 依赖：HA-0048 Retrieval State 契约。
- 边界：不启用 Agentic RAG、外部/语义检索、缓存或模型化 Reflect。
- 机器契约：`specs/v1/retrieval-state-v2.schema.json`；目标 DAG fixture 覆盖“选项目 → 优化 → 面试题”，并验证策略准入、预算硬停、身份缓存和完成条件负例。
- 迁移：HA-0048 的 `retrieval-state@1` 保持只读兼容；v2 新增 goals、strategy_tiers、budget、cache_policy 和 Agentic stop reason，不猜测回填历史目标或预算。
- 复审：mymacclaude Approved（HEAD 98b0b26）；收尾补强 completed 目标必须 user_confirmation=confirmed，并对 validator 错误码去重。
