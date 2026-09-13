# HA-0022：规划/执行图谱能力覆盖审计

状态：completed（2026-09-13）。把用户提供的 Plan / TAO / State / Replan 图谱逐项映射到当前 HarnessAgent 的真实实现，消除把受限本地切片描述成通用 Agent 的风险；验收证据位于 `harness/evidence/HA-0022/`。

## 目标

建立一份从图谱模块到当前实现、离线合同和未授权边界的可审计矩阵，并修正技术债与运行时事实不一致的表述。

## 范围

1. 在 `PLAN_REPLAN_CONTROL.md` 记录 Goal、Context、Choice、TAO、Evidence、Gap、Checkpoint、Replan 与六出口的覆盖状态。
2. 修正 TD-021/TD-022 的完成事实；为仍缺少通用 TAO runtime 的风险登记 TD-023。
3. 完成 L0 文档、任务注册表、链接和状态验证，并保存可复核 Evidence。

## 非目标

- 创建新的 Agent Loop、模型路由、动态 Action、权限或外部连接；
- 将离线 reducer、固定 Node 或 Event 日志冒充运行时 TAO；
- 关闭 HA-0001、HA-0008 或任何要求用户/凭证授权的阻塞项。

## 验收

- 每个图谱模块都有真实来源和覆盖状态，已实现/离线/未授权不混淆；
- 任务、状态、技术债与文档不再把 HA-0014、ADR-0019/0020 说成过期状态；
- 文档链接、JSON Schema 与现有回归通过，零运行时能力变更。
