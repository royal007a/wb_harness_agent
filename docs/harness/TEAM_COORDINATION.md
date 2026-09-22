# Team Task、Handoff 与 Gate（ADR-0033）

## 当前可用边界

ADR-0033 提供的是一个本机、单进程、local-admin 的协作控制面纵切：它把一次可交付工作固定为 `Team Task → Handoff → Gate`，而不是把团队约定留在某段 Agent 对话里。

它**没有**连接 Agent Runtime、模型、MCP、外部工具、Daemon、消息投递、身份认证、Workspace/Channel 服务或跨设备执行。运行时状态固定报告 `agent_runtime=not_connected`、模型调用和外部工具调用均为零；因此不能把它称为“已运行的 Agent Team”。

## 对象与不变量

| 对象 | 持久化内容 | 核心不变量 |
|---|---|---|
| Team Task | Channel/Thread 引用、目标、requirements、scope、停止条件、Gate、负责人、租约、版本 | requirements 与 Gate 在创建后不修改；scope 只是交接约束，不是执行授权 |
| Handoff | 任务版本、requirements/Gate 摘要、决策、产物引用、证据、缺口、风险、下一步 | 只追加；只有有效 lease 的负责人可写；不能换一份 requirements/Gate 伪装交付 |
| Gate decision | reviewer、任务版本、摘要、证据、原因、`pass/reject/needs_human` | 只追加；仅预设 reviewer 可写；Gate pass 才表示 done |
| Closure | 关闭人、原因、时间 | `closed` 只表示停止跟踪，不是验收通过；已关闭 Child 不再阻塞父项 |

输入拒绝凭证样式内容。请求和响应不保存 Source 正文、模型推理或工具输出；`artifact_refs` 只保存外部产物引用及 SHA-256。所有写请求都必须携带 `Idempotency-Key`。

## 状态流与父子约束

```text
todo --claim(lease)--> in_progress --handoff + submit--> in_review --pass--> done
                                  ^                         |\
                                  |                         | \--needs_human--> in_review
                                  +-------- reject ---------+

todo / in_progress / in_review --close(reason)--> closed
```

- SQLite `BEGIN IMMEDIATE` 使并发 `claim` 只有一个成功；expired lease 会清除负责人并退回 `todo`。
- `in_progress` 的 Handoff、submit 与 close 都要求同一负责人持有未过期 lease。
- `in_review` 只允许指定 Gate reviewer 决策；关闭只允许负责人或 reviewer。真实身份/权限校验属于后续阶段。
- 父 Task 有 `todo`、`in_progress` 或 `in_review` Child 时，submit 和 Gate `pass` 都被拒绝；`done` 和 `closed` Child 不阻塞。
- 任何状态写入使用 `expected_task_version` 乐观并发控制；旧版本返回 `TEAM_TASK_VERSION_CONFLICT`，调用方必须重新读取。

## API 与审计

| 方法 | 端点 | 用途 |
|---|---|---|
| GET | `/api/local/team/runtime` | 明示当前只有控制面、零外部调用 |
| GET / POST | `/api/local/team/tasks` | 列表或创建冻结的 Team Task |
| GET | `/api/local/team/tasks/{task_id}` | 读取 Task、Child、Handoff、Gate decisions |
| POST | `/{task_id}:claim` | 原子认领执行租约 |
| POST | `/{task_id}/handoffs` | 追加版本绑定的交接 |
| POST | `/{task_id}:submit` | 有 Handoff 且 Child 结束后进入审核 |
| POST | `/{task_id}/gate-decisions` | 指定 reviewer 作出三出口裁决 |
| POST | `/{task_id}:close` | 记录原因后停止跟踪，不等于交付 |

机器契约是 [`team-coordination.schema.json`](../../specs/v1/team-coordination.schema.json)，静态 OpenAPI 位于 [`openapi.yaml`](../../specs/v1/openapi.yaml)。稳定错误至少包括 `TEAM_TASK_CLAIM_REQUIRED`、`TEAM_TASK_VERSION_CONFLICT`、`TEAM_TASK_CHILDREN_OPEN` 与 `TEAM_TASK_GATE_FORBIDDEN`。

## 后续顺序

1. Inbox / attention / work mark：先做权限过滤、执行租约、同 Thread 消息合并和人类纠正优先；不可用“每条消息都唤醒 Agent”替代。
2. freshness：把 read sequence 与发送/提交的版本检查放在同一事务，过期草稿须补读再决定。
3. Agent/Computer/Session：只有 Runtime、身份、工具政策和证据链经过独立 L3 审查后，才将 Handoff/Gate 接到真实执行。
4. 子 Agent：默认只读、父权限收窄、预算/取消/结果引用；不能把本地 Task 对象误称为已经并发运行的 Subagent。
