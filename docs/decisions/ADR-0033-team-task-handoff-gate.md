# ADR-0033：以独立 Team Task 建立交接与 Gate 的最小纵切

状态：Proposed

日期：2026-09-22

## 背景

用户提供的 Agent Team 设计将长期协作的最小闭环定义为 Task、Handoff 与 Gate。五份 Harness 课程材料也共同表明：外部状态、失败恢复、提醒、审批与 Subagent 都必须有可见的任务边界和证据，不能依赖模型对话记忆。

既有 `Task` / `Run` 是 P0 CSV 分析的 Product 契约。直接扩张它会破坏固定适配器的范围，也会把研发治理 Work Item 与产品协作对象混合。

## 决定

增加独立的本地 `team-task@1` 控制面纵切：

- Team Task 固定 Channel/Thread、requirements、scope、stop conditions 与 Gate；创建后对 requirements/Gate 生成摘要绑定，并拒绝凭证样式的协作元数据。
- `claim` 使用 SQLite `BEGIN IMMEDIATE` 原子认领和有期限 lease；没有有效认领不能写 Handoff 或提交审核。
- Handoff 是仅追加的、绑定 task version 与 requirements/Gate digest 的记录；它携带决策、产物摘要、证据、剩余工作、风险和下一动作。
- `submit` 只允许带有效 Handoff 的任务进入 `in_review`；父任务存在未完成 Child 时稳定拒绝。
- Gate 独立记录 `pass / reject / needs_human`。只有指定 reviewer 对当前版本给出 `pass` 才进入 `done`；`reject` 回到 `in_progress`，`needs_human` 保持 `in_review`。
- `close` 记录关闭人、原因和时间并进入 `closed`，以便取消的 Child 不再阻塞父项；它绝不表示交付或 Gate pass。
- 本切片只持久化协作控制状态；不启动模型、Daemon、Agent Runtime、外部工具、自动审批、自动委派或真实身份认证。

## 后果

- 交付/验收有稳定且可审计的机器边界，能支持后续 Inbox、freshness、work mark、execution lease 与 Child delegation。
- 这不是完整 Agent Team：没有 Workspace/Channel 服务、用户鉴权、Agent 运行、消息派发、Computer/Daemon 或跨设备迁移。
- `scope` 目前是协作契约字段，不替代工具执行时的权限策略；真正的工具调用仍须经过现有 Policy Gateway。

## 验收

机器规格：[`team-coordination.schema.json`](../../specs/v1/team-coordination.schema.json)。

测试必须覆盖：幂等创建、原子认领与 lease 到期、未知字段/凭证样式/越权拒绝、requirements/Gate/version 绑定、Handoff 追加、父项阻塞及 closed Child 放行、Gate 三出口、重启持久化和 OpenAPI 契约一致性。
