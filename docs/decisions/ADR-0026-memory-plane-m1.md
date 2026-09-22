# ADR-0026：长期记忆 M1 以来源证据优先的独立 Memory Plane 实现

状态：Proposed（本地受限实现）
日期：2026-09-19

## 背景

普通 RAG 不能解决跨会话偏好变化、历史决策或可追溯纠错；但把完整聊天自动写入向量库也会产生敏感数据、错误尝试、过期事实和不可解释结论。本项目的 `plan.md` 已定义 P2 Memory Plane，首个可验证阶段是 M1：Memory Bank、Source Evidence、Fact、审计、去重、纠错/撤回/删除和跨 bank 隔离。

## 决策

先实现一个不调用模型的本机 M1：管理员显式提供受限的 Source Evidence 与原子 Fact；系统不从完整对话自动抽取、不写 Observation/Opinion/Mental Model，也不做 Reflect、向量、图、外部 RAG 或权威事实替代。

- `Memory Bank` 固化 `ws_local`、local admin、作用域、数据分类、保留天数与 `memory-policy@1`；请求体不能指定工作空间或所有者。
- Source 保存内容、来源引用、发生时间、分类、摘要和到期时间；Fact 必须绑定 Source、类型、置信度、时间与状态。
- Source/Facts 以 `active → superseded|retracted` 演化。显式 supersede 不覆盖旧 Fact；retract 保留审计而不参与召回；delete 物理清除可控正文/Fact，留下无正文 tombstone 与审计。
- Recall 仅为读回审计：在单一 Bank 内进行状态、保留期、有效期过滤及确定性 keyword/temporal 排序，返回不含原始 Source 正文的 Evidence Bundle；它不等同 M2 双路检索。
- 拒绝 Restricted、凭证样式内容、未知字段及 Public Bank 的 Internal Source。M1 审计不是 Product Event；未来接入 Product Task/Run 必须先建模身份、权限、预算与 Event 关联。

## 后果

M1 能证明记忆不是对话 dump：每条可召回 Fact 有来源、时间、状态和删除路径，且不同 Bank 不会互相返回。它仍是单用户 SQLite 原型，未满足生产身份/租户、异步模型抽取、索引重建、语义/图检索、RRF/rerank、权威源冲突处理或 Reflect 的要求；这些边界不得借本 ADR 宣称已完成。
