# Agentic RAG 适配说明

## 迭代式检索 vs Agentic RAG

| 能力 | 迭代式检索 | Agentic RAG |
|---|---|---|
| 下一步 | 根据已有结果补 Query | 自主选目标、Query、数据源、工具和验证路径 |
| 路径 | 通常固定数据源/方法 | 根据 Gap、权限和预算动态调整 |
| 停止 | 预设轮数、覆盖和重复率 | 结合证据充分性、预算、风险和用户目标 |
| 当前 Harness 位置 | HA-0048 Retrieval State | 后续控制器，默认关闭 |

## 最小充分检索

把复合请求拆成 `goal_id`，每个目标必须满足三个可验收条件：至少 1 个关键 Claim；证据不依赖其他目标产出；可以单独产生用户可交付结果。目标完成还必须满足每个 Claim 达到 `min_evidence_per_claim` 且没有 blocking open Gap。目标之间以 `depends_on` 组成 DAG；用户确认是否进入下一个目标记入状态。示例 fixture 是 `goal:select-project → goal:optimize-project → goal:interview-questions`，分别对应“选项目、优化项目、生成面试题”；模型参与拆解时属于模型决策，必须经过同一 Gate。

## 动态策略与预算

预算上限在 Run 创建时固定，控制器只能递减使用，不能提高上限。可用策略层级也在 Run 启动时做快照，运行中 Gate 状态变化不会解锁更高 tier。预算快照沿用 Retrieval State 的 `elapsed_ms/token_count/tool_calls/cost_minor`，并记录每轮剩余预算。策略按成本递增：

1. `local_keyword`：M1/M2-A FTS5 和精确详情；
2. `local_temporal_graph`：时间过滤与显式两跳图；
3. `admitted_semantic_or_external`：仅在 ADR-0031 Gate 为 admitted、来源/权限/费用已绑定时可选。

每次升级都记录 `strategy_change`、触发 Gap、预计收益和预算影响；升级只在已快照且 admitted 的 tier 内进行。预算耗尽是硬停止，不能因为“最小目标可能已满足”而继续花费；`budget_exhausted` 优先于效果类停止原因。预算不足但尚有剩余时可以降级，记录 `budget_degraded`，依次降级为已有 Evidence Bundle、澄清或“未评估”，不能自动换 Provider、放宽域名或扩大工具权限。契约从 HA-0048 的 `retrieval-state@1` 迁移到 `retrieval-state@2`：旧状态只读保留，升级时新增 goals/strategy_tiers/budget/cache 字段，不回填猜测的目标或预算。

## 缓存边界

缓存依赖真实身份体系，在本项目有主体/租户映射前保持禁用。启用后的键直接复用 HA-0048 的 `query_key`，并绑定 `source_policy_digest + corpus_version + as_of_bucket + methods + effective_permission_set_digest + subject_id/tenant_id`；不另造 `normalized_query`，避免规范化分叉和 PII 进入键。缓存值只允许结构化 Evidence Bundle 和来源引用；禁止 negative cache（空结果不缓存），不得缓存未脱敏原文、凭证或最终答案。`as_of` 使用有效期桶并配合 TTL；撤回、supersede、删除、版本变化和权限变化通过 evidence_id 反向索引清理相关条目。当前项目尚未实现缓存，不能以“有缓存设计”宣称性能提升。

## 端到端评测

分层记录：

- 效果：答案成功率、关键 Claim Evidence Coverage、无证据结论率、冲突处理准确率；
- 体验：端到端 p50/p95，从用户请求到可交付答案；以及“首个有用结果时间”（第一个满足最小目标交付条件的结果）；
- 成本：轮数、工具调用、Token、费用、缓存命中率；
- 对照：同一 fixture、K、预算下比较单轮、HA-0048 固定迭代和 Agentic RAG；冷缓存与热缓存分开报告。

`answer_success` 先用固定 rubric 标注关键 Claim 是否正确、证据是否足够、是否出现无证据结论；若使用 LLM judge，必须用人工标注集校准并报告一致性。Agentic 路径至少重复运行 5 次并给出置信区间。“更好”定义为质量不低于单轮基线且成本不超过预算上限，或在质量/首个有用结果时间/成本三维 Pareto 前沿占优。检索毫秒数只是 trace 子指标，不能单独作为 Agent 性能结论。

## 当前状态

本页只做架构适配；当前已实现的是 HA-0048 契约和 M1/M2-A/M3-A 本地确定性路径。Agent 自主选择数据源/工具、语义召回、缓存和模型 Reflect 均未实现。
