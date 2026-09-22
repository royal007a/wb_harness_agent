# HA-0037：Team Task、Handoff 与 Gate 最小纵切

状态：completed

风险：high（协作状态与验收语义；不涉及外部执行）

## 目标

以独立本地控制面对象实现 Agent Team 的最小交付闭环：Task 的要求/范围/停止条件、原子认领、可审计 Handoff、父子任务阻塞和 Gate 三出口。

## 范围

1. 先冻结 `specs/v1/team-coordination.schema.json` 和 ADR-0033；
2. SQLite 持久化 Team Task、Handoff 与 Gate Decision；
3. 提供本地 create/list/detail、claim、handoff、submit、gate-decision API；
4. 实施无模型、无外部工具的合成测试、OpenAPI 验证和重启持久化验证；
5. 通过后先发布本机，再发布公网，并保留无密 Evidence。

## 非目标

- 不实现真实 Agent Runtime、Subagent、Workspace/Channel/Thread 消息服务、Inbox、Daemon、身份认证或跨设备迁移；
- 不实现自动审批、模型自动组队、自动 Handoff、真实外部副作用或策略放行；
- 不修改既有 P0 Product Task/Run 或把 `harness/tasks.json` 研发任务当成 Team Task。

## 完成条件

- 契约和实现严格一致；所有改变状态的请求都要求 Idempotency-Key，并拒绝凭证样式协作元数据；
- 只有有效认领的执行者可交接/提交，只有 Gate reviewer 可裁决，且版本不匹配被拒绝；
- 父任务有未结束 Child 时不能提交；`pass/reject/needs_human` 状态转换正确，`closed` 记录原因且不被误认为交付；
- 全量测试、OpenAPI、双环境健康和端点验证通过，Evidence 已入库。

## 验收结果

- `tests/test_team_coordination.py` 覆盖创建幂等、并发 claim、lease 到期、Handoff/version 绑定、父子阻塞、close、Gate 三出口、重启、OpenAPI 与敏感输入拒绝；7 项通过。
- 完整 `harness/verify.sh` 为 225 passed、12 skipped、0 failed；四项既有合成 Memory 评测均通过，semantic Gate 仍为 `not_admitted`。
- 本机与公网均备份 SQLite 后发布。两端 health 正常，Team Runtime 均为 `agent_runtime=not_connected`、模型/外部工具调用为 0；公网未认证入口保持 401。
