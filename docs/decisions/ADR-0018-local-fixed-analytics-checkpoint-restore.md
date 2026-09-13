# ADR-0018：本地固定分析器的受限 Checkpoint / Restore

- 状态：Accepted（受限本地纵向切片，实施与 L3 验收进行中）
- 日期：2026-09-13
- 触发：用户在 HA-0018 隔离恢复探针验收后，明确授权把 checkpoint/restore 接入一个受限 Product adapter。

## 决策

批准只为 `engine_mock_analytics` 实现一个固定恢复点：`resource.inspect` 完成、输入资源摘要已验证、确定性统计指标已生成之后，且在产物发布之前。该恢复点不是模型上下文、任意代码执行器或动态 Plan 的快照。

当原 Run 以 `failed` 或 `expired` 终结且保有该 Checkpoint 时，本地用户可显式创建新的恢复 Run。恢复 Run 必须绑定到同一 Product Task、CSV 资源 ID 与 SHA-256、适配器 descriptor、有效权限、剩余预算和 Checkpoint 内容摘要。任何绑定漂移都拒绝，绝不降级为重算或静默新 Run。旧 Run 的终态、事件和产物不被修改。

接口将是本地受限的 `POST /api/local/runs/{run_id}:restore`，需要空 JSON 对象与 `Idempotency-Key`。它不接受候选计划、目标、资源、权限或参数；`cancelled`、`succeeded` 和跨 Task 场景一律拒绝。普通 `rerun` 仍是独立的新 Run 语义。

## 后果

- 本地固定分析器可以通过受控 checkpoint/restore 契约提供一个真实的恢复纵向切片，但这不批准通用 Replan 或多引擎恢复。
- SQLite 将增加只追加的 Checkpoint 记录；State 只含受控结构化统计和摘要，不能写入原始 CSV、目标、Prompt、凭证或模型思维过程。
- 必须通过 L3 兼容性、故障注入、取消、幂等、重启和浏览器验证，才可将现状文档从“仅探针”改为“有限本地恢复”。
- 真实模型、远程沙箱、生产灾备、多租户授权、动态 Plan/TCC API 仍是独立后续工作，不能从本 ADR 推导为已批准。
