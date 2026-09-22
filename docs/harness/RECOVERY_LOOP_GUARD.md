# Recovery Loop Guard（ADR-0034）

## 适用范围

这是衔接 ADR-0033 Team Task/Handoff/Gate 的本机恢复**决策**记录，不是 Agent 执行器。它不会发模型请求、调用工具、恢复 Checkpoint、修改外部状态或自动批准权限。

运行时固定返回：`agent_runtime=not_connected`、模型/工具调用均为 `0`、`automatic_recovery_execution=false`。

它也不同于 [Plan / Replan 执行控制](PLAN_REPLAN_CONTROL.md)：后者只处理固定 CSV Product Run 的白名单恢复路径；本页只处理 Team Task 的审计与交付前控制，不扩张既有 Product API。

## 一次失败的四个位置

| 位置 | 保存什么 | 不能替代什么 |
|---|---|---|
| 失败点 `failure_point` | operation 引用、稳定错误码、观测时间、Evidence | 只说明哪里暴露失败，不证明原因 |
| 根因假设 `root_cause_hypothesis` | 分类、假设文字、低/中置信度、Evidence | 不是确认事实，也不等于回滚位置 |
| 回滚 Checkpoint `rollback_checkpoint` | `verified` 的外部引用/摘要，或明确 `unavailable` | 日志、Task version 和 Handoff 都不是可恢复 Checkpoint |
| Replan 起点 `replan_start` | 下一个重新作决策的位置、理由、是否要新输入 | 不必等于失败点或回滚点 |

服务端从错误目录生成 `error-contract@1`：稳定 `error_code`、`retryable`、推荐下一步和最少 Evidence 类别。调用方只能提交错误码，不能覆盖目录判断。

## Try / Confirm / Cancel

```text
failure → Recovery Case(open) → Try(candidate only) → Confirm(no execution)
                                                  │
                                                  └→ Cancel(audit only)

Confirm → Team Handoff → Team submit → Gate pass → Recovery Case(resolved)
```

- **Try**：只产生一个 `proposed` 候选（重试幂等步骤、回滚到已验证 Checkpoint、或澄清后停止）；验证有效 Task lease、冻结版本、输入摘要、无工具权限快照和剩余硬预算。没有工具调用。
- **Confirm**：重新核对 Task、Checkpoint、权限快照、预算与输入摘要；任何漂移都会拒绝候选。成功只变为 `confirmed_pending_handoff`，并不表示动作已执行或任务已交付。
- **Cancel**：把当前候选标为 `cancelled`，追加不可变 cancel audit，并终止 Case；不修改 Team Task，不回滚文件，也不尝试补偿。

Case 创建和 Try/Confirm/Cancel/Observation/Handoff 关联都使用幂等键；改变的 Case 使用 `expected_case_version` 乐观并发控制。

## 防循环规则

| 类型 | 条件 | 系统动作 | 明确不会做什么 |
|---|---|---|---|
| 硬熔断 | 达到 turn、截止时间、候选尝试、同一 operation+签名连续失败上限，或取消 | Case 进入 `needs_human` 或 `cancelled`，拒绝新候选 | 不重试、不加预算、不扩权限、不调用工具 |
| 软 Reminder | 同一 operation+签名连续失败两次且尚未硬熔断 | 追加“换策略或转人工”提醒 | 不自动选新路径、不会自动创建 Task/Handoff |
| 可验证进展 | 显式 `verified_progress` Observation 且带 Evidence | 重置连续失败计数 | 不代表 Gate 通过或自动结束 Case |

Observation 只存 operation 引用、不可逆 SHA-256 签名和 Evidence 引用；不存原始工具参数、密钥、模型思考或外部 stdout/stderr。

## 交付约束

在 `confirmed_pending_handoff` 后，负责人必须先写同一 Team Task 的 Handoff。关联时系统重验 Handoff 的 owner、Task version、requirements/Gate 摘要和当前 scope 摘要。随后仍需按 ADR-0033：

1. `submit` 进入 `in_review`；
2. 指定 reviewer 对同一 Task 记录带 Evidence 的 Gate `pass`；
3. 才可以用该 Gate decision 将 Case 标为 `resolved`。

`Try`、`Confirm`、Reminder、Observation 或一个“看似成功”的外部过程，均不能绕过这条路径。

## API

| 方法 | 端点 | 用途 |
|---|---|---|
| GET | `/api/local/recovery/runtime` | 固定零执行运行时边界 |
| GET / POST | `/api/local/recovery/cases` | 列表或创建带 Error Contract/四位置的 Case |
| GET | `/api/local/recovery/cases/{case_id}` | 读取 Case、候选、Observation、Reminder、Cancel audit |
| POST | `/{case_id}/observations` | 追加失败或可验证进展，评估软/硬循环控制 |
| POST | `/{case_id}:try` | 生成候选恢复路径，不执行 |
| POST | `/{case_id}:confirm` | 重验绑定，不执行 |
| POST | `/{case_id}:cancel` | 只记录取消与停止状态 |
| POST | `/{case_id}:link-handoff` | 将已确认 Case 绑定到相同 Task 的 Handoff |
| POST | `/{case_id}:complete` | 仅在同 Task Gate pass 后结束 Case |

所有写请求都需要 `Idempotency-Key`。完整字段见 [`recovery-loop-guard.schema.json`](../../specs/v1/recovery-loop-guard.schema.json)。

## 非目标和后续门槛

未实现：真实 Checkpoint snapshot/restore、实时取消、模型/工具 runtime、外部状态对账、身份认证/授权、动态权限批准、通用 Plan 生成、自动 Replan 以及自动 Gate。

未来接入真实运行时前，必须把每个外部操作关联到幂等键和可验证副作用状态，独立验证工具取消/超时/不确定提交、真实权限与预算政策、Checkpoint restore 和人工 Gate 故障路径；不得将本地记录表述为真实 Agent 已完成恢复。
