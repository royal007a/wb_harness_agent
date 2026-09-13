# Agent 引擎适配器契约

## 目的

适配器把平台 Task/Run 协议翻译成特定 Agent 引擎调用。它不是业务服务，不拥有平台状态机，也不能绕过 Tool Runtime。

## 生命周期接口

适配器实现以下语义接口；传输方式留待 ADR 决定：

| 接口 | 输入 | 输出 |
|---|---|---|
| `describe` | 无 | 适配器版本、协议版本、能力、限制、健康信息 |
| `start_run` | Task 快照、Run、工具描述、资源句柄、预算 | 有序 Engine Events |
| `checkpoint_run` | Task/Run/资源快照与已验证中间状态 | 版本化、无密且可摘要绑定的 Adapter State；平台负责持久化 |
| `restore_run` | Run、兼容的 Checkpoint、剩余预算 | 后续 Engine Events |
| `cancel_run` | Run、原因、截止时间 | 已接收/已终止/无法终止 |
| `probe` | 标准能力探针 | 结构化探针结果 |
| `cleanup` | Run 与沙箱引用 | 清理结果 |

接口必须幂等。重复 `start_run` 不能创建两个活动执行；重复取消不能产生新副作用。

## 能力声明

能力使用版本化键，至少包括：

- `actions.code`
- `actions.tool_call`
- `agents.managed`
- `transport.streaming`
- `state.checkpoint`
- `state.restore`
- `control.cancel`
- `output.structured`
- `artifacts.files`
- `telemetry.usage`

每项取值不能只写 true/false，还需声明限制，例如支持的语言、最大并发、是否保持解释器状态、取消粒度和结构化输出版本。

## Replan 准入（Proposed）

`assess_replan_adapter` 只读取 `describe()` 的 capability descriptor，不发起探针或执行。它把同时支持 `state.checkpoint`、`state.restore`、`control.cancel`、`output.structured` 的 Adapter 标为 `eligible_for_runtime_probe`；任何缺失均为 `ineligible`。两种结论都不等于用户可用或生产批准，`runtime_enabled` 始终为 false。

`LocalAnalyticsAdapter.describe()` 现已声明一个版本化固定 Checkpoint 格式与同 Task restore 能力。ADR-0018 批准 `resource.inspect` 后的确定性统计状态恢复；ADR-0019 仅在 `ARTIFACT_PUBLICATION_FAILED` 时使用相同状态创建白名单候选 Plan，并要求失败 Event Evidence、Try/Confirm/Cancel、摘要绑定、L3 故障注入与显式用户动作；它们都不是通用 Replan 准入。其他适配器仍必须先通过独立 L3 checkpoint/恢复/取消/副作用故障注入与用户批准。

## 输入约束

适配器只接收：

- 已解析且版本固定的 Agent Spec；
- 不可变 Task 快照与本次 Run；
- 受限资源句柄，不是宿主真实路径；
- 平台签发的 Tool Capability；
- 模型路由结果和短期凭证引用；
- 时间、轮次、Token、费用与沙箱限制。

## Engine Event

适配器产生的原始事件先映射为平台事件，再持久化。最低事件集：

```text
run.started
model.call.started | model.call.completed | model.call.failed
code.proposed
code.execution.requested
tool.call.requested
checkpoint.proposed
artifact.proposed
child_run.requested
run.result.proposed
run.failed
```

适配器不得自行发出平台 `run.succeeded`；控制面只有在结果与产物验证通过后才能提交成功终态。

## 错误分类

| 类别 | 示例 | 平台处理 |
|---|---|---|
| `invalid_request` | 能力或配置不支持 | 不重试 |
| `model_transient` | 限流、临时不可用 | Step 级受限重试 |
| `model_fatal` | 鉴权、模型不存在 | Run 失败 |
| `tool_error` | 工具业务失败 | 交给 Agent 或策略决定 |
| `sandbox_violation` | 越权、资源超限 | 立即终止并审计 |
| `budget_exceeded` | 时间、轮次、Token、费用 | 明确终止 |
| `cancelled` | 用户或策略取消 | 清理并终止 |
| `adapter_bug` | 非预期异常、协议错误 | Run 失败并隔离版本 |

## Smolagents 映射提案

- `CodeAgent` 对应 `actions.code`，P0 只开放受控数据工具。
- `ToolCallingAgent` 仅在 P1 作为只读检索 Child Run 候选。
- `managed_agents` 映射为 `child_run.requested`，不得成为不可见的内部调用。
- 本地解释器只用于开发探针；生产 P0 要求远程隔离 executor。
- MCP 工具先进入平台 Tool Registry，再把受限能力交给适配器。
- 具体 SDK 类名、构造参数和版本由实现期能力探针固定，不写入核心协议。

## 契约测试

Mock 与每个真实适配器必须通过：重复启动、事件顺序、取消、超时、预算耗尽、工具拒绝、检查点不兼容、结果校验失败、清理失败和未知事件测试。
