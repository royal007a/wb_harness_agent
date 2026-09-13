# ADR-0020：本地确定性 Replan 的 Gap State

状态：Accepted（2026-09-13）。这是一项 ADR-0019 的可观测性与状态完整性补充，不扩大其执行授权。

## 背景

当前本地 TCC 已持久化 PlanRevision、失败 Event Evidence 和 ReplanAttempt，但“原 Run 为什么不能完成”仍主要由错误码表达。图中的 Gap State 要把缺少什么、影响哪个计划节点、能否由哪个已注册 Action 消除组织为可审计状态，而不是让 Replan 只凭错误码猜测。

## 决策

1. 当固定统计 Run 在 checkpoint 后发生 `ARTIFACT_PUBLICATION_FAILED` 时，控制面在同一失败提交中持久化一条 `gap@1`：`required_by=node_publish`、`type=evidence`、`severity=core`、`resolvable_action_ids=[artifact.publish]`、`status=open`。它只含 ID、分类和受控引用，不含目标、错误堆栈、CSV 或 Prompt。
2. Replan 提案必须读取同一失败 Event 的 open Gap；不存在、状态已不是 open，或 Gap 与白名单恢复 Action 不一致时拒绝创建 Attempt。`GET /replans/{id}` 同时返回该 Attempt 的 Gap 投影。
3. 只有绑定恢复 Run 的固定产物校验、发布和最终回答均成功后，控制面才把源 Run 对应 Gap 标为 `resolved`，并在新 Run 写入 `gap.resolved` 事件。Try、Cancel、失败的 Confirm、失败的恢复 Run 都不得解决 Gap。
4. Gap 不重写源 Run、失败 Event、Evidence、Checkpoint 或 Plan；若用户取消 Attempt，Gap 仍保持 open，允许后续以同一固定边界创建新 Attempt。

## 非目标

- 通用 Gap 推断、LLM 根因分析、用户编辑 Gap、跨 Run 自动合并或用 Gap 绕过权限/预算；
- 非 `ARTIFACT_PUBLICATION_FAILED` 的新恢复路径；
- 以 `resolved` 声称输入或模型结论真实，只表示该固定产物发布缺口已由受控路径消除。

## 验收

源失败、提案、Try/Cancel、Confirm 漂移和恢复成功/失败均通过持久化反例测试；浏览器 Evidence 展示 open Gap 的受限方案与成功后的 `gap.resolved` 事件。模型、网络和任意代码调用保持 0。
