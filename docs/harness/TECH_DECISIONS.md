# 技术决策索引

本页同时列已接受和正在评审的决策。只有 `Accepted` 才是当前制度；`Proposed` 不得被描述为已实现或已冻结。被替代的 ADR 必须在原文和索引中明确标记，不删除历史。

| ADR | 状态 | 决策摘要 |
|---|---|---|
| [ADR-0001](../decisions/ADR-0001-harness-is-structure-template.md) | Accepted | Harness 只作为研发治理结构 |
| [ADR-0002](../decisions/ADR-0002-provider-neutral-control-plane.md) | Proposed | 核心采用厂商中立控制面契约 |
| [ADR-0003](../decisions/ADR-0003-optional-engine-adapters.md) | Proposed | 引擎通过可选适配器接入 |
| [ADR-0004](../decisions/ADR-0004-durable-async-task-state.md) | Proposed | 使用持久异步任务状态机 |
| [ADR-0005](../decisions/ADR-0005-policy-before-side-effects.md) | Proposed | 所有副作用在执行前通过策略与授权 |
| [ADR-0006](../decisions/ADR-0006-controlled-codeact-p0.md) | Proposed | 以受控 CodeAct 数据分析作为 P0 |
| [ADR-0007](../decisions/ADR-0007-remote-sandbox-for-model-code.md) | Proposed | 模型生成代码使用远程隔离沙箱 |
| [ADR-0008](../decisions/ADR-0008-vision-model-route.md) | Proposed | 图片理解路由使用 Doubao-Seed-2.1-Turbo，探针通过后启用 |
| [ADR-0010](../decisions/ADR-0010-adapter-sandbox-probes.md) | Accepted（开发探针） | Adapter 边界、Colima VM 和明确标记的脚本模型探针；不开放真实路由 |
| [ADR-0011](../decisions/ADR-0011-local-child-run-orchestration.md) | Accepted（本地演示） | 一层 Child Run 扇出、最多 3 并发、固定资料、失败/取消/预算/恢复 |
| [ADR-0012](../decisions/ADR-0012-baidu-netdisk-oauth-connector.md) | Accepted（本地 OAuth 准备） | 官方 OAuth 授权码、Keychain 凭证、无密 SQLite 审计；不爬取分享链接 |
| [ADR-0013](../decisions/ADR-0013-baidu-netdisk-local-configuration-helper.md) | Accepted（本机准备） | TTY 无回显配置助手将 Secret 写入 Keychain；不通过聊天/文件传递凭证 |
| [ADR-0015](../decisions/ADR-0015-local-deterministic-intent-preflight.md) | Accepted（本地受限实现） | 只识别 CSV 分析的无模型 Intent Contract、缺槽澄清与显式提交门禁 |
| [ADR-0016](../decisions/ADR-0016-intent-model-evaluation-gate.md) | Proposed | 模型化意图路由先通过合成去标识离线评测与影子门禁 |
| [ADR-0017](../decisions/ADR-0017-plan-evidence-gap-checkpoint-control.md) | Proposed | Plan/Evidence/Gap/Checkpoint 统一为执行控制面，Replan 采用 TCC |
| [ADR-0018](../decisions/ADR-0018-local-fixed-analytics-checkpoint-restore.md) | Accepted（受限本地切片，已验收） | 固定统计边界的同 Task Checkpoint / Restore；不开放通用 Replan |
| [ADR-0019](../decisions/ADR-0019-local-deterministic-replan-tcc.md) | Accepted（受限本地切片） | 仅产物构建失败的固定候选 Plan 与 Try/Confirm/Cancel；不开放 Plan 编辑或通用 Agent Replan |
| [ADR-0020](../decisions/ADR-0020-local-replan-gap-state.md) | Accepted（受限本地切片，已验收） | 为唯一白名单失败持久化 `gap@1`；仅成功绑定恢复可解决 |
| [ADR-0021](../decisions/ADR-0021-local-agent-lab-preparation.md) | Accepted（本地准备切片） | 无密 Profile、SQLite Session 与确定性 POST SSE；真实模型/Provider 仍未启用 |
| [ADR-0022](../decisions/ADR-0022-local-provider-agent-chat-runtime.md) | Accepted（受控本地运行时） | Provider/Model/Agent/Session/Exchange 与默认关闭的协议 Adapter；工具和 Child Run 未接入 |
| [ADR-0023](../decisions/ADR-0023-research-multi-agent-simulation.md) | Accepted（本地模拟切片） | 三角色 Child Agent、第一方 Skill 摘要、受控只读 Tool 和父级证据汇总；不是实际 Claude SDK 或金融数据系统 |
| [ADR-0024](../decisions/ADR-0024-native-claude-research-runtime.md) | Proposed | 原生 Claude SubAgent、Plugin Skill、进程内 MCP 资料工具与父子事件映射；默认外部运行关闭，真实连通仍需 L3 Evidence |
| [ADR-0025](../decisions/ADR-0025-external-skill-isolation.md) | Proposed（本地受限实现） | 不可信外部 Skill 固化为严格 ZIP，并仅在默认关闭的一次性禁网非 root Colima 容器运行 |
| [ADR-0026](../decisions/ADR-0026-memory-plane-m1.md) | Proposed（本地受限实现） | 来源优先的 Memory Bank / Source Evidence / Fact M1，支持撤回删除与受限证据读回，不启用模型或向量 |
| [ADR-0027](../decisions/ADR-0027-memory-context-m2a.md) | Proposed（本地受限实现） | M1 之上的显式 Fact Capsule、FTS5 关键词目录和按 ID 详情回读；不包含模型摘要或语义检索 |
| [ADR-0028](../decisions/ADR-0028-explicit-memory-graph-m3a.md) | Proposed（本地受限实现） | 由显式 Fact 支撑的 Entity / Relation、至多两跳的图/时间 Evidence Path；不包含自动抽取、消歧或自然语言 GraphQA |
| [ADR-0029](../decisions/ADR-0029-explicit-entity-catalog-m3b.md) | Proposed（本地受限实现） | 同 Bank canonical/alias 的 casefold 精确 Entity 目录；只返回 resolved/ambiguous/not_found，不自动消歧 |
| [ADR-0030](../decisions/ADR-0030-memory-temporal-read-safety.md) | Proposed（本地受限实现） | 统一 M1 Recall、M2-A Context/Detail 的 Source/Fact `as_of` 发生时间与有效期过滤 |
| [ADR-0031](../decisions/ADR-0031-semantic-retrieval-admission-gate.md) | Proposed（本地受限实现） | M2-B semantic/vector/RRF 的版本化 fail-closed Admission Gate；当前不含 Provider、模型、网络或索引 |
| [ADR-0032](../decisions/ADR-0032-fact-lineage-evidence.md) | Proposed（本地受限实现） | 以明确 Fact ID 返回有界 supersede 历史，解释新旧结论变化并严格区分当前适用性 |
| [ADR-0033](../decisions/ADR-0033-team-task-handoff-gate.md) | Proposed（本地受限实现） | 独立 Team Task 的 lease、Handoff、父子阻塞、Gate 三出口与 closure；不连接真实 Agent 或身份系统 |
| [ADR-0034](../decisions/ADR-0034-recovery-loop-guard.md) | Proposed（本地受限实现） | Team Task 的 Error Contract、四位置恢复记录、Try/Confirm/Cancel、硬熔断/软 Reminder 与 Handoff/Gate 回接；零自动执行 |

## 待决策

[ADR-0009：本地工作台初版](../decisions/ADR-0009-local-workbench.md) 已在用户实现授权范围内 Accepted：FastAPI、SQLite、原生前端和单进程本地工具。以下服务选型待决项继续适用于生产与真实 Agent 阶段。

- 首个实现语言与服务边界；
- 关系数据库、队列与对象存储；
- 身份与工作空间隔离强度；
- 内部适配器协议（进程内、RPC 或消息）；
- Smolagents 版本、执行器能力与首个真实适配器最终批准；
- `doubao-seed-2.1-turbo` 图片输入端点与能力探针；
- 遥测、评测和远程沙箱具体技术。

这些问题应由验证性证据驱动，不在规格文档中暗设答案。
