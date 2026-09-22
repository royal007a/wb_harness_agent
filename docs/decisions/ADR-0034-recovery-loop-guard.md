# ADR-0034：把恢复决策和防循环做成 Team Gate 之前的受限旁路

状态：Proposed（本地受限实现）

日期：2026-09-22

## 背景

失败后的“再试一次”很容易把失败点误当根因、把日志误当 Checkpoint，并在没有新证据时无限重复同一个操作。已有 ADR-0019 的 Product Replan 是固定 CSV 适配器的白名单 TCC；它不能承担 Team Task 的恢复记录，也不能被扩张为开放式 Agent Replan。

ADR-0033 已提供 `Team Task → Handoff → Gate`，但此前没有把一次失败的恢复假设、冻结边界、重复失败与交付验收稳定地连起来。

## 决定

新增独立的 `recovery_loop_guard@1` 本机控制面，并且只关联已有 Team Task：

- `Error Contract` 由服务端目录按稳定错误码派生 `retryable`、推荐下一步和所需 Evidence；调用方不能把不可重试错误伪装为可重试。
- 一个 `Recovery Case` 分别持久化失败点、根因**假设**、回滚 Checkpoint 和 Replan 起点。四者使用不同字段和证据，根因永远带 `low` 或 `medium` 置信度，不被记录成既定事实。
- 创建时冻结 Team Task 版本、requirements/Gate/scope 摘要、输入摘要和固定“无工具执行”权限快照。`scope` 仍不是运行时授权；本切片不存在可扩大权限的字段。
- `Try` 只创建经校验的候选策略，`Confirm` 再检查 Task claim/版本、Checkpoint、固定权限摘要、turn/时间/尝试预算和输入摘要；二者都不启动恢复、模型、工具或外部副作用。`Cancel` 只追加取消审计并把候选终止，不尝试补偿。
- 通过 turn、总时间、候选次数、同一 operation+签名连续失败和取消实施硬熔断。连续失败但尚未命中硬上限时，只追加“换策略或转人工”的软 Reminder；Reminder 不修改权限、预算或 Task。
- `Confirm` 不是交付。恢复结果必须另行写入同一 Task 的 append-only Handoff，正常 `submit`，并由原 Gate `pass` 后才能把 Recovery Case 标为 `resolved`。

## 后果

- 失败处理现在有可验证、可审计且不会自动执行的决策边界；“重试成功”不能越过已有 Handoff/Gate。
- 这不是可运行的 Agent Loop、通用 Replan 引擎、真实 Checkpoint Restore、工具取消器或授权系统。`external_model_calls=0`、`external_tool_calls=0`、`automatic_recovery_execution=false` 是运行时固定事实。
- `actor_id` 仍只是 local-admin 协议字段；真正身份、工具策略、外部副作用幂等性和 L3 故障演练仍须独立决策和验证。

## 验收

机器规格：[`recovery-loop-guard.schema.json`](../../specs/v1/recovery-loop-guard.schema.json)。

测试必须覆盖：错误目录稳定性；四位置分离；Task/输入/权限/Checkpoint/预算 Confirm 绑定；Try/Cancel 的零执行；连续失败 Reminder；turn/时间/候选/重复操作/取消硬停止；以及 Handoff 和同一 Task Gate pass 之前不能 resolved。
