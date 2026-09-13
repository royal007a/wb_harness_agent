# HA-0020：本地确定性 Plan/Replan TCC 产品纵向切片

状态：completed（2026-09-13）。依据用户在当前话题对“无模型动态 Plan/Replan 受限纵向切片”的明确批准，以及 ADR-0019；验收证据位于 `harness/evidence/HA-0020/`。

## 目标

把图中的 `Plan/G4C → TAO → Checkpoint → Try/Confirm/Cancel → Replan` 以受限、可验证的方式接入当前固定 CSV 分析器。只处理 checkpoint 后的已知产物构建失败，保留 ADR-0018 的直接恢复作为更窄入口。

## 范围

1. SQLite 持久 PlanRevision、Event Evidence 与 ReplanAttempt；所有对象通过 `execution-control@1` 机器合同校验，且仅保存摘要/受控引用。
2. 基于实际 `ARTIFACT_PUBLICATION_FAILED` Event 创建唯一白名单恢复计划：`checkpoint.verify → artifact.publish → run.final_answer`；不接收请求方 Plan。
3. 实现带幂等键的 create / Try / Confirm / Cancel / 查询 API；Confirm 比较并交换完整绑定并创建新的恢复 Run。
4. 恢复 Run 在发布前执行零副作用 checkpoint 验证，并记录 Plan/Replan 关联事件；不重复 `resource.inspect`。
5. 工作台展示固定候选与三步 TCC 操作；补齐 L3 故障、篡改、竞态/幂等、取消、重启与浏览器 Evidence。

## 非目标

- 模型、联网、任意代码、自动根因判断、动态工具发现或用户/模型编辑 Plan；
- 非 `ARTIFACT_PUBLICATION_FAILED` 的自动 Replan、跨 Task/资源/权限/预算/适配器恢复；
- 取消已确认的 Attempt、覆盖源 Run/产物，或把该流程泛化为真实 Agent runtime。

## 验收

- 没有实际失败 Event Evidence、根因不在白名单、Checkpoint 或六类绑定不兼容时，无法创建/确认新的 Run；
- Try 只写 Attempt 状态和摘要，Confirm 才且仅能创建一个绑定的恢复 Run；Cancel 不能产生 Run；
- Confirm 后的 Run 只执行固定验证与两个既有受控发布动作，数值回算、预算、权限和旧 Run 不变量保持成立；
- API、Schema、UI、L3 契约/故障/浏览器、静态检查和 Evidence 通过，模型/网络/任意代码计数为零。
