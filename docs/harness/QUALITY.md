# 质量规范

## 分级质量门禁

| 级别 | 适用变更 | 必须通过 |
|---|---|---|
| L0 | 文档、注释 | 链接、术语、范围和敏感信息检查 |
| L1 | 单模块、无协议变化 | L0 + lint、类型检查、单元测试 |
| L2 | API、状态、适配器、工具 | L1 + 契约测试、集成测试、迁移和安全测试 |
| L3 | 权限、身份、数据删除、发布链路 | L2 + 端到端、故障注入、性能、恢复和人工审查 |

风险升级时采用更高门禁，不得因改动行数少而降级。

## 测试矩阵

- **契约**：请求/响应 Schema、未知字段、版本兼容、稳定错误码。
- **状态机**：合法迁移、并发租约、重试、取消、超时、恢复、终态不可变。
- **执行控制**：候选 Action 白名单、硬前提、六出口、Evidence/Gap/Checkpoint 可信状态传播、TCC 与失效集合。
- **适配器**：能力声明、事件映射、检查点、取消传递、错误分类。
- **工具**：输入校验、权限拒绝、超时、幂等、副作用范围和输出清理。
- **CodeAct**：禁网、只读输入、输出路径、资源上限、取消、沙箱销毁和数值回算。
- **视觉**：固定 OCR/表格/图表样例、尺寸边界、结构化输出与能力不匹配；模型判断不能代替确定性校验。
- **安全**：越权、提示注入、路径穿越、SSRF、凭证泄漏和恶意产物。
- **评测**：固定数据集、评分器版本、随机性设置、基线和置信区间。
- **运维**：队列积压、依赖中断、降级、回滚、备份和恢复。

## Agent 质量要求

- 输出可追溯到输入资源、工具结果和配置版本。
- 事实性任务必须提供引用；引用需能定位到不可变资源版本。
- 结构化输出必须通过 Schema；失败不得伪装成自然语言成功。
- 达到轮次、时间、Token 或费用上限后使用明确退出原因。
- 模型评审只作为一个信号，关键规则由确定性检查器验证。
- 图表中的关键数字必须从源数据回算，不能只从视觉模型回答采信。
- 评测集和生产请求隔离，防止答案泄漏和过拟合。
- 模型化意图路由先使用版本化合成去标识夹具；候选结果只保存 case ID 和结构化预测，必须经过摘要绑定、类别覆盖、阈值与影子模式校验，不能以固定样例通过替代生产准入。
- Replan 评测必须覆盖失败点与根因不一致、Checkpoint/资源/策略不兼容、权限或预算扩大、取消竞态、失效传播与无效恢复拒绝；固定函数引擎不能以审计点冒充可恢复 Checkpoint。
- ADR-0018 的本地恢复必须额外覆盖 Checkpoint 后故障、同 Task 新 Run、原 Run 终态不可变、SQLite 重启、幂等、资源/Task/适配器/权限/预算/状态摘要篡改拒绝与 cancelled 拒绝；固定统计状态须重新回算，不能把不匹配状态降级成新分析结果。
- `supported` Claim 的 Evidence 必须存在、已验证且没有未解决反证；`restorable` Checkpoint 与 `confirmed` Replan 必须通过摘要绑定的反例契约测试。
- ADR-0019 的本地 TCC 切片还必须覆盖：失败 Event 白名单、非空请求拒绝与控制对象脱敏、Try/Cancel 无 adapter/Product Run/工具副作用、Confirm 的 CAS 去重、Cancel 无 Run、Try 后绑定漂移过期、重启与浏览器 `checkpoint.verify` / 不重复 `resource.inspect`。
- ADR-0020 的本地 Gap State 还必须覆盖：失败 Event 与唯一 core Gap 的原子创建、缺失/已解决/字段不兼容 Gap 的提案拒绝、Try/Cancel/漂移/恢复失败不解决 Gap，以及仅成功绑定恢复在新 Run 写入 `gap.resolved`；浏览器 Evidence 必须确认该状态转换且模型、网络、任意代码调用仍为零。
- ADR-0021 Local Agent Lab 必须覆盖：严格 Schema/未知字段、凭证样式输入拒绝、Provider/Model/Agent 启用依赖、Session 隔离、消息顺序与幂等冲突；POST SSE 必须出现 `delta → done`，浏览器使用 `fetch` 而不是 EventSource；页面取消仅停止显示，且模型/Provider/网络/工具调用始终为零。
- ADR-0022 Agent Runtime 必须覆盖：独立 `runtime_*` 表、严格 credential reference 格式、默认 `MODEL_RUNTIME_DISABLED` 的 Exchange 失败、无 synthetic assistant 内容、Provider readiness 零网络、同键回放、最近 `2 × max_context_turns` 上下文、协议 Adapter 成功/空响应/超时错误映射与断开后的可审计终态。真实 Provider 启用前还必须补齐 L3 凭证解析、请求最小化、取消、预算、网络失败、TLS 和数据外发审查。
- ADR-0023 Research Agent Simulation 必须覆盖：请求/Agent/Skill/Tool Schema，三个角色与 Skill 摘要的 Task 快照，Child 资源与权限收窄、两步预算、Action/Observation/Final 事件、摘要漂移和越权拒绝、全局并发、部分失败、取消、重跑和重启；父报告只能引用独立复算通过的 Child artifact，且模型/Provider/网络/外部工具调用恒为零。浏览器必须显示这不是 Claude SDK 或真实金融系统。
- ADR-0024 Native Claude Research 必须覆盖：默认 gate 在 SDK query/CLI/Keychain/HTTP 之前拒绝，SDK/CLI/MCP/插件摘要固定，父 `Agent` 与三个 Child `AgentDefinition` 的工具/Skill/预算收窄，SDK parent-tool-use→Child Run 映射、消息大小限制、来源证据 Schema、未知 source ID 拒绝、PDF/域名/响应大小/超时/凭证引用故障和父报告 partial 语义。真实 L3 还必须记录同一模型版本下的三 Child 委派、并发观测、资料外发、工具取消、费用上限、网络/TLS 故障、PDF OCR 缺口、重启/回滚与引用人工审查；在此之前不得标记引擎 available。
- ADR-0025 External Skill Runtime 必须覆盖：默认 gate 在包读取/Docker 前拒绝；ZIP 只允许固定 manifest/entrypoint、拒绝路径穿越/链接/额外文件/凭证样式内容；内容摘要漂移拒绝；幂等登记/执行、输入输出上限和清理审计稳定。可用 Colima 环境还必须跑真实 L3：非 root、禁网、宿主路径/Docker socket/环境秘密不可见，并验证容器清理。任何网络、依赖或 Product Run 接入须新增 L3 验收。
- ADR-0026 Memory Plane M1 必须覆盖：严格 Bank/Retain/Recall Schema、固定 local ownership、跨 Bank 零泄漏、来源/Fact 幂等与去重、时间/状态过滤、Fact supersede、Source retract/delete 的级联失效、正文删除后的无正文 tombstone/audit、SQLite 重启和敏感/分类/越权输入拒绝。M1 的 keyword/temporal read-back 不得被评为 M2 vector/semantic/graph/RRF/Reflect 通过。
- ADR-0027 Memory Context M2-A 必须覆盖：SQLite FTS5 从 canonical active Fact 重建、Capsule 只含 caller-transient recent turns 与 Fact-derived 摘要、目录 ID 到 detail 的精确回读、detail 不可复制原始 Source、Bank/状态/时间重验证、supersede/retract/delete 索引传播、重启、索引不可用的稳定错误和合成 recall/保真/泄漏评测。M2-A 不得被评为自动摘要、语义/vector/graph、RRF/rerank、模型回答质量或完整长期记忆通过。
- ADR-0028 Memory Graph M3-A 必须覆盖：Entity/Relation 的严格 Schema、同 Bank active Fact 支撑、两端 Entity 和时间窗口验证、最多两跳的有向/反向路径、逐边 Fact/Source provenance、环路跳过、跨 Bank 零泄漏、supersede/retract/delete 后派生 Node/Edge 失效或物理清理、幂等、SQLite 重启和合成多跳/时间/删除评测。M3-A 不得被评为自动实体抽取/消歧、自然语言 GraphQA、图排序、语义/vector、模型答案质量或完整图知识库通过。
- ADR-0029 Memory Entity Catalog M3-B 必须覆盖：canonical/alias casefold 精确匹配、`resolved`/`ambiguous`/`not_found`、可选类型筛选、同 Bank/Fact/Source/时间重验证、supersede/retract/delete 传播、敏感和未知字段拒绝、重启、零原始 Source/跨 Bank 名称泄漏及合成目录评测。M3-B 不得被评为自动实体抽取、模糊/语义/向量匹配、实体合并/消歧、自然语言 GraphQA、图排序、模型答案质量或完整知识图谱通过。
- ADR-0030 Memory temporal read safety 必须覆盖：M1 Recall、M2-A Context 和 Detail 在相同 Bank/`as_of` 对 Source `occurred_at`、Fact `occurred_at`/有效期采用一致可见性过滤；future Source/Fact、FTS5 candidate、retract/delete、跨 Bank、重启和零原始正文的合成反例必须通过。它不构成 semantic/vector/RRF/rerank、自动摘要、Entity Resolution、GraphQA、Reflect 或最终回答质量通过。
- ADR-0031 Semantic Retrieval Admission Gate 必须覆盖：not-admitted 必为 disabled/模型和外部调用零、无完整语料/外发/删除/离线评测/成本 Evidence 的 admitted 状态被拒绝、Runtime Gate 与版本化状态一致、重启仍 fail closed。它不构成 embedding、vector、RRF/rerank、语义命中、数据外发审查、删除演练、性能成本或真实 L3 通过。
- ADR-0032 Fact Lineage 必须覆盖：已知 ID 的 active→superseded 有界链、当前/历史 applicability、Source/Fact `as_of`、跨 Bank、删除/撤回、深度/环路、重启与零正文。它不构成自动冲突裁决、自然语言查询、模型判断或 Reflect 通过。
- ADR-0033 Team Coordination 必须覆盖：未知字段/凭证样式内容拒绝、幂等创建、原子 claim 与 lease 过期释放、requirements/Gate/task version 绑定、Handoff 只追加、父项的开放/closed Child 行为、Gate 三出口与 reviewer 拒绝、重启持久化、OpenAPI 一致性及零模型/零外部工具状态。它不构成真实身份认证、Agent Runtime、Subagent 并行、消息调度、自动审批或权限执行通过。

## 完成定义 DoD

任务只有在以下条件全部满足时才能标为 `completed`：

- 验收条件逐项通过，非目标未被擅自纳入；
- 对应质量级别的自动检查全部通过；
- 安全、数据和权限影响已评估；
- 失败、取消、超时和回滚路径已验证；
- 文档、契约、迁移和运维说明与实现同步；
- Evidence 包含环境、版本、命令/步骤、结果和时间；
- 没有未登记的技术债或临时豁免。

## Evidence 最小集合

```text
harness/evidence/<task_id>/
├── manifest.json
├── test-results.*
├── security-results.*
├── evaluation-results.*
└── release-or-review-note.md
```

并非每个任务都需要全部文件，但 `manifest.json` 必须解释哪些门禁适用、哪些不适用及原因。
