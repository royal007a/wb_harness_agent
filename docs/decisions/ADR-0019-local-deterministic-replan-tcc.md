# ADR-0019：本地固定分析器的确定性 Plan/Replan TCC 切片

状态：Accepted（2026-09-13，用户在当前话题明确批准“无模型的动态 Plan/Replan 受限纵向切片”）。

## 背景

ADR-0018 已证明固定统计状态可在 `resource.inspect` 后以严格摘要绑定恢复，但它没有 PlanRevision、失败根因 Evidence、Try/Confirm/Cancel 或候选路径，不能称为动态 Replan。通用 Agent Replan 仍需要真实 adapter、模型、工具副作用和额外安全批准，当前不具备这些前提。

本决策只把一个已知、可回算的故障分支接入 Product Run：固定统计已 checkpoint，随后受控产物构建失败。此时目标、资源、权限、适配器和预算均不变；控制面只能选用版本化的本地恢复计划，而不能接受用户或模型提交的新计划。

## 决策

1. `engine_mock_analytics` 只在源 Run 因 `ARTIFACT_PUBLICATION_FAILED` 失败且 checkpoint 仍完整时允许创建 ReplanAttempt。失败 Event 会固化为 Event Evidence；其他失败码、没有失败 Event、已取消/成功 Run 一律拒绝。
2. 控制面为该 Attempt 持久化两份不可变 PlanRevision：已执行的固定基线计划和唯一允许的恢复计划。恢复计划固定为 `checkpoint.verify → artifact.publish → run.final_answer`，其中 `checkpoint.verify` 是零副作用控制检查，不占工具步骤预算；调用方不能上传、编辑或替换节点。
3. TCC 必须显式走完：
   - **Try** 只重验 checkpoint、DAG、失败 Evidence、适配器、资源、权限和剩余预算，并写入摘要；不得创建 Run、调用适配器、模型、网络或工具。
   - **Confirm** 以候选 Plan、checkpoint、Task/资源、适配器、有效权限与剩余预算的摘要比较并交换；仅成功时创建一个新的恢复 Run 并绑定 ReplanAttempt。新 Run 在发布前再次执行 `checkpoint.verify`。
   - **Cancel** 只废弃未确认 Attempt；不改原 Run、不删除 checkpoint、不补偿，也不允许取消已确认 Attempt。
4. 每个 checkpoint 最多物化一个恢复 Run，不论它来自 ADR-0018 的直接恢复还是本 ADR 的 Confirm；两条入口不能绕过彼此的去重。

## 后果

- 工作台可让用户查看固定候选并显式 Try、Confirm 或 Cancel；任何 Confirm 之前没有 Product Run 副作用。
- 该切片具备真实持久 Plan/Attempt 和 TCC 语义，但它仍不是自由的计划器：没有模型、网络、任意代码、跨 Task/资源/引擎、计划编辑、自动根因推断或通用 Action 选择。
- 新的 `checkpoint.verify` 事件仅证明固定状态与绑定重新通过，不宣称重新执行 `resource.inspect` 或生成新知识。
- 若以后支持其他失败类型、可编辑 Plan 或真实 Agent adapter，必须另立 ADR，完成权限/副作用/取消/回滚 L3 演练，并不得扩大本切片的授权。

## 验收证据

完成后写入 `harness/evidence/HA-0020/`：TCC 反例、CAS/幂等、篡改与预算拒绝、取消、重启、浏览器路径和全量回归。模型、网络和任意代码调用计数必须为零。
