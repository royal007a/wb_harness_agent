# Plan / Replan 执行控制合同

状态：部分实现。ADR-0019 已为本地固定分析器实现一个白名单、无模型的 Plan/Replan TCC 切片；通用动态 Plan/Replan 仍为 Proposed。

本页把 Plan、TAO、Evidence、Gap、Checkpoint 和 Replan 组织为同一个控制面模型。它不引入第五个 Agent 框架，也不把研发 Harness 状态混入 Product Task/Run。

## 现状与适用边界

- `engine_mock_analytics` 支持一个固定的、持久化的 checkpoint：`resource.inspect` 后的确定性统计状态。只有 `failed`/`expired` 源 Run 才可由 `POST /api/local/runs/{run_id}:restore` 创建同 Task 的恢复 Run；它不接受候选 Plan，也不允许资源、权限、预算或适配器版本漂移。
- `engine_local_research_demo` 是固定函数 Child Run 演示，支持取消和整树重跑，不生成动态计划。
- 当前没有真实模型或开放式动态 Action 选择。ADR-0019 的运行时只对 `ARTIFACT_PUBLICATION_FAILED` 选择一份固定的恢复 Plan（`checkpoint.verify → artifact.publish → run.final_answer`）；它不接收用户/模型候选节点，也不适用于任何其他失败。其余 reducer、Schema 和夹具仍是离线控制面合同。

只有适配器已验证 `state.checkpoint=true`、`state.restore=true`、`control.cancel=true` 后，才可申请通用动态 Replan 接入。ADR-0018 的固定恢复不满足“动态重规划”语义，不能据此跳过 Try/Confirm/Cancel 或开放目标 Replan API。

在发起通用 Replan 探针前，控制面先用 `assess_replan_adapter(describe())` 检查 checkpoint、restore、cancel、structured output 四项声明；它最多给出 `eligible_for_runtime_probe`，绝不自动开启**通用动态 Replan**。当前 `LocalAnalyticsAdapter` 已声明固定 restore 能力，因此可进入该离线准入层；实际只按 ADR-0018 开放受限本地恢复。

## 图谱对应与能力覆盖（2026-09-13）

用户提供的“Agent 规划与执行知识图谱”描述的是一个控制闭环，而不是要求所有方块都已成为开放式 Agent runtime。下表区分当前事实、离线合同和未获授权能力，避免把受限切片误述为通用能力。

| 图中模块 | 当前落点 | 覆盖状态 | 不可外推的边界 |
|---|---|---|---|
| `Goal` | 不可变 Product Task、资源版本、权限和预算摘要 | 已实现（固定本地分析器） | Replan 不能修改目标、资源、权限或预算；变化必须新建 Task |
| `Context` / `Plan` | `PlanRevision`、失败 Event Evidence、Checkpoint 与受控 Gap 引用 | 已实现（白名单路径） | Context 不是任意历史/RAG/长期记忆，且不保存 Prompt 或原始 CSV |
| `Choice` / Action 选择 | `LocalAnalyticsAdapter` 固定节点；恢复只允许 `checkpoint.verify → artifact.publish → run.final_answer` | 已实现（固定选择） | 没有模型驱动的候选枚举、排序或动态工具发现 |
| `Action State` / `Observation State` | Run Event 只追加记录动作、异常和进度；纯 reducer 仅用于离线合同验证 | 部分实现 | 运行时没有通用 TAO 状态 reducer 或跨引擎 Action 编排 |
| `Evidence` | 失败 Event 作为持久 Evidence；结果与 Checkpoint 受摘要绑定 | 已实现（该路径） | 不等于外部来源真实性、时效性或完整 Claim 验证 |
| `Gap State` | `gap@1` 与同一失败 Event 原子关联；`node_publish` 的 `evidence/core` 缺口 | 已实现（ADR-0020） | 只覆盖 `ARTIFACT_PUBLICATION_FAILED`；不能由调用方创建、编辑或用作通用根因结论 |
| `Checkpoint` | `resource.inspect` 后持久统计状态、绑定兼容摘要、同 Task 恢复 | 已实现（ADR-0018） | 不保存模型/解释器状态，也不支持跨引擎恢复 |
| `Replan` / 回溯 | `ReplanAttempt`、Try/Confirm/Cancel、摘要 CAS、派生新 Run | 已实现（ADR-0019/0020） | 仅一个失败码和一个固定回滚/起点；非开放式重规划 |
| 六出口、可信状态传播、最大信息增益 | Schema、纯 reducer、合成夹具与评测 | 离线合同 | 未注册到 Product runtime，不能声称已动态决定 `continue/clarify/retry/replan/...` |

下一项真正的运行时扩展必须先关闭 TD-023，并在批准后为目标引擎建立 capability probe、持久 Action/Observation 合同、L3 副作用/取消/恢复故障注入以及回滚演练；不能从本表的“部分实现”直接推出开放权限。

## G4C：每次决策的四个门

```text
Goal      = 不可变 Product Task 的目标、成功标准、资源版本、权限与预算
Context   = 已验证/失效的 Observation、Evidence、Gap、Control 与 PlanRevision
Choice    = 从注册 Action 中经前置条件、权限、预算和风险过滤后的唯一选择
Checkpoint= 已通过 Gate 的提交边界；有兼容恢复能力才可标为 restorable
```

`Goal` 绝不由 Plan/Replan 原地改写。输入资源、目标、权限或新鲜度要求发生实质变化时，创建关联的新 Product Task，而不是伪装为 Replan。

## 领域对象与不变量

机器 Schema 位于 [`execution-control.schema.json`](../../specs/v1/execution-control.schema.json)。对象只保存 ID、摘要、分类和受控引用；不保存目标原文、Prompt、密钥或模型思维过程。

| 对象 | 用途 | 不变量 |
|---|---|---|
| `PlanRevision` | 节点、依赖、候选 Action、硬/软前提、成功/Evidence 要求的不可变快照 | Run 只绑定一版；Replan 创建新版本与新 Run |
| `Evidence` | Resource、Artifact、Event 或 Tool Result 的可定位来源 | 不可变、带摘要、分类、验证和可信状态 |
| `Claim` | Fact / inference / hypothesis | `supported` Claim 必须至少有一条 supporting Evidence 且为 `verified`；反驳/撤回不能维持 verified |
| `Gap` | 影响节点/Claim 的 slot/resource/evidence/permission/checkpoint 缺口 | 标明严重度与可消除该缺口的注册 Action |
| `CheckpointProjection` | Checkpoint 的 Evidence/Gap/状态摘要和恢复能力投影 | 同时固定 checkpoint、adapter、resource、权限与剩余预算摘要；`verified` 不等于 restorable |
| `ReplanAttempt` | 失败、根因证据、回滚点、失效集合、候选计划与 TCC 决定 | Try/Confirm 摘要与 confirmed Run 必须绑定；它不改变旧 Run 终态 |

`Task` 意图不可变、`Run` 终态不可覆盖、Event 只追加、权限和预算只能收窄仍是最高优先级不变量。

## TAO 与六种出口

```text
Think: 读取 G4C 状态，判断目标、Gap、候选路径与停止条件
Action: 仅选择已注册且满足硬前提、权限和预算的 Action
Observation: 写入结果、异常、进度与 Evidence 引用
Reducer: 更新可靠性、Gap、Control，并决定唯一出口
```

出口是确定性枚举，不是模型自由文本：

| 出口 | 条件 |
|---|---|
| `continue` | 存在通过硬门禁的注册 Action |
| `finish` | 成功标准与 Evidence Gate 都通过；禁止为循环继续调用工具 |
| `clarify` | 核心 Gap 无任何当前允许 Action 可消除 |
| `retry` | 路径仍成立、动作幂等且失败确属瞬态；受次数限制 |
| `replan` | 新事实推翻路径/假设或路径无法继续；必须先完成 Try |
| `interrupt` | 没有安全路径、外部副作用状态不明、权限/预算耗尽或用户取消 |

“最大信息增益”只能在硬门禁之后排序合法候选，不能突破工具白名单、权限、前置条件或预算。

## Evidence / Gap / Checkpoint 传播

可靠性只有 `verified`、`dirty`、`invalid`：上游 `invalid` 会使所有依赖项 `invalid`；上游 `dirty` 会使依赖项至少 `dirty`。只有重新执行并通过 Gate 才能回到 `verified`。这阻止 Replan 从失效的中间结果继续。

事实、推断与假设必须分型。Evidence 能提高可追溯性和约束无依据输出，但不保证来源真实、未过期或推理正确；最终 Claim 仍须检查来源质量、反证、适用范围和证据覆盖。

Checkpoint 必须是已验证提交点，不是普通日志。恢复前重验适配器、工具、权限、输入资源和兼容摘要；任何不匹配都明确失败，禁止猜测恢复。

## Replan：四个位置与 TCC

失败点、根因点、回滚点、重规划起点分别保存，不能互相替代：

1. 失败点：`event_id + step_id + error_code + observed_at`，仅说明症状。
2. 根因点：计划节点、Evidence refs、假设与置信度；证据不足不得自动重规划。
3. 回滚点：最晚的 `verified`、兼容 Checkpoint，且在最早失效节点之前或相等。
4. Replan 起点：重新决策/执行的第一个节点；若它早于当前 Checkpoint，必须使用更早 Checkpoint 或拒绝恢复。

`ReplanAttempt` 用 Try / Confirm / Cancel 流程：

- **Try**：只读验证 DAG、失效集合、候选计划摘要、权限子集、剩余预算和 restore 兼容性；不得执行工具或产生副作用。
- **Confirm**：以 `plan_digest + checkpoint_digest + adapter/tool/resource 摘要 + effective_permissions + remaining_limits` 绑定。`confirmed` 状态还必须保存 Try 摘要、Confirm 绑定摘要和新 Run 引用。任何变化使确认失效；新 Run 预算不得超过原 Checkpoint 的剩余预算。
- **Cancel**：只撤销本次 Attempt 并失效待确认令牌；不改变原 Run、不删除 Checkpoint，也不等于自动补偿。

ADR-0020 为 ADR-0019 的唯一白名单失败增加实际 Gap State：`ARTIFACT_PUBLICATION_FAILED` 创建 `node_publish` 的 core open Gap；提案必须引用它；只有恢复 Run 的固定产物路径成功才把它改为 resolved。它不把错误码扩展成通用根因推断，也不允许用户填写/编辑 Gap。

ADR-0019 已实现本地受限 API：`POST/GET /api/v1/runs/{run_id}/replans`、`GET /api/v1/replans/{id}`、`POST /api/v1/replans/{id}:try`、`POST /api/v1/replans/{id}:confirm`、`POST /api/v1/replans/{id}:cancel`。每个写入操作都需幂等键；Confirm 使用比较并交换保护摘要绑定。它们只接受空对象，且只有白名单故障会产生唯一候选；不能外推为目标 API 的通用 Plan 编辑能力。

ADR-0034 的 [Recovery Loop Guard](RECOVERY_LOOP_GUARD.md) 复用了“四个位置 + Try/Confirm/Cancel”的控制原则，但它是独立的 Team Task 旁路：不创建 Product Run/PlanRevision、不执行 restore，并额外要求 Handoff + Gate pass 才能 resolved。两者不得互相表述为通用动态 Replan。

## 当前离线验证

[`backend/execution_control.py`](../../backend/execution_control.py) 是纯函数 reducer；不读取数据库、不调用模型或工具、不创建 Run。[`fixtures/execution-control-evaluation-v1.json`](../../fixtures/execution-control-evaluation-v1.json) 含合成去标识的固定情形，覆盖六出口、可信状态传播、当前本地适配器的 restore 拒绝、权限/预算扩大拒绝、兼容恢复与 TCC 转移。运行：

```sh
.venv/bin/python harness/evaluate_execution_control.py \
  --fixture fixtures/execution-control-evaluation-v1.json \
  --output /tmp/execution-control-evaluation.json
```

准入指标：失败定位证据覆盖、失效传播漏检率（目标 0）、安全 Checkpoint 命中、无效恢复次数（目标 0）、重规划后的有效进展，以及次数/时间/Token/费用预算。真实恢复适配器必须再通过 L3 契约、故障注入、取消、权限、资源变更和恢复演练。

HA-0018 另提供 [`checkpoint_restore_probe.py`](../../harness/checkpoint_restore_probe.py)：它在独立内存中演练 `Plan → checkpoint → Try → Confirm → restore`，并校验状态/适配器/资源/权限/预算摘要。该 probe 没有注册到 `Service.adapters`，输出明确 `runtime_route_registered=false` 和 `product_run_created_or_restored=false`；它仍是合同纵向验证，不是可用引擎。ADR-0018 的实际 Product 纵向切片仅复用“摘要绑定的 Checkpoint/恢复”原则，保持固定计划，故不把 probe 或恢复端点说成完整 TCC Replan。
