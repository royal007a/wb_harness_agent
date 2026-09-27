# ADR-0049：以最小目标、动态预算和可失效缓存约束 Agentic RAG

## 状态

Proposed（设计适配，未启用 Agentic RAG）

## 关系与边界

迭代式检索是“上一轮结果不足时补查”的检索机制；Agentic RAG 是能自主选择下一步目标、Query、数据源、工具、验证方式和停止时机的完整控制形态。前者是后者的一个循环组件，不应把固定三轮检索描述成 Agentic RAG。

## 决策

1. **最小充分检索**：先把用户请求拆成可独立交付的 `goal_id`，每个目标必须至少有一个关键 Claim、独立证据链和独立可交付结果；完成要求每个 Claim 达到 `min_evidence_per_claim` 且无 blocking Gap。目标以 `depends_on` 组成 DAG，用户确认是否进入下一目标必须入状态；模型拆解同样属于受 Gate 约束的模型决策。
2. **端到端目标函数**：优化 `answer_success`、关键 Claim 证据覆盖、端到端 p50/p95 延迟和每答案成本；召回延迟只是分解指标，不能替代用户可感知的成功率。
3. **动态预算**：预算上限在 Run 创建时固定，策略层级也在启动时快照；控制器只能向下花费，不能提高上限或因运行中 Gate 变化解锁高 tier。预算耗尽硬停，不能与“最小目标满足”并列为继续条件；预算不足但未耗尽才允许降级并记录 `budget_degraded`。
4. **缓存只缓存可复用证据**：身份体系未就绪前缓存保持禁用。启用后直接复用 HA-0048 `query_key`，并绑定有效权限集合 digest、subject/tenant、source policy/corpus 版本、有效期桶和方法；禁止 negative cache，Evidence ID 反向索引负责撤回/supersede/delete 传播失效。当前缓存未实现。
5. **Agentic 决策可审计**：每次选择目标、数据源、工具、验证路径、升级/降级和停止都写入 Retrieval State/Run Event，并引用 Gap、预算快照和 Evidence ID。决策不修改权限，不能绕过 Admission Gate。

## 评测

在同一数据集、同一 K 和同一预算下，比较单轮、固定迭代和 Agentic RAG 三条路径：答案成功率（固定 rubric/校准后的 judge）、关键证据覆盖率、错误/无证据结论率、首个有用结果时间、p50/p95 端到端延迟、Token/工具调用/费用、平均轮数和缓存命中率；冷/热缓存分开。Agentic 路径重复至少 5 次并给出置信区间；“更好”要求质量不低于基线且成本不超过上限，或进入质量/首结果时间/成本 Pareto 前沿。没有这些对照数字，不得标记 Agentic RAG available。

## 当前边界

本项目目前只有 HA-0048 的 `retrieval-state@1` 契约和 M1/M2-A/M3-A 确定性本地路径；HA-0049 的 `retrieval-state@2` 设计新增目标/策略/预算/缓存字段，但尚未接入运行时。没有 Agentic source/tool selection、semantic/vector/RRF/reranker、外部数据、缓存或模型化 Reflect。真实启用仍需 ADR-0031 Admission Gate、权限/预算、数据外发审查和 L3 Evidence。
