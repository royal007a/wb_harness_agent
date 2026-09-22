# ADR-0037：以受限 Session Continuity Handoff 延续 Agent 身份而非上下文正文

状态：Proposed（本机受限实现）

日期：2026-09-22

## 背景

HA-0033/0034/0035/0036 已把 Team Task、Gate、授权边界、attention 和 freshness 变为可验证状态，但同一 protocol Agent 在一次工作结束、重启或人工决定换代后，还没有一份可由下一段 Session 使用的、受限且可审计的交接记录。

直接保存/复制聊天、模型上下文或工作目录会混淆 Team 控制面与 Runtime；自动根据 token 利用率切换 Session 又要求尚未接入的 Runtime telemetry。两者都不应在没有身份、数据和 Runtime 准入的情况下假装实现。

## 决定

新增独立 `local_team_session_continuity@1` 控制面：

- 一个 `Team Session` 只绑定既有 Workspace、Channel 与 protocol Agent identity。它不是 Provider/模型会话，也不保存 prompt、消息正文、工具输出、工作目录、凭据或上下文窗口。
- Session Handoff 只能由该 Session 的所属 protocol identity 手工发起，使用乐观版本；它会 retire 旧 Session，并由服务端从当前可访问的 Team Task、Gate、Attention 与 read cursor **生成**有界 Snapshot。创建时的 Snapshot 不可改写；唯一可单调补充的字段是一次性 `consumed_by_session_id` 审计关联。
- Snapshot 只包含 Task/Attention ID、版本、状态、Thread ID、latest/read sequence；不复制 Task 标题/目标/Handoff 正文、消息正文或附件。`current_task` 仅在恰有一个有效执行租约时出现；否则以 `owned_tasks` 明示多个开放工作，避免伪造“当前任务”。
- 同一 identity 在同一 Channel 同时最多一个 active Team Session。新 Session 如继承 Handoff，必须是同一 Workspace/Channel/identity、未被消费且对应旧 Session 已 retired；服务端在创建时重新生成当前 Snapshot，历史 Handoff 只作为审计起点，不能替代当前 freshness 检查。
- Session Handoff 不会创建/修改/认领 Team Task，不会清除 work mark，不会改变 Gate，不会自动恢复或派发 Run。Task 写路径继续服从 ADR-0036 freshness。
- Runtime telemetry、自动 Session rotation、自动 resume、消息历史和真实身份认证全部固定为未连接/关闭。

## 后果

- 系统能交接可验证的“有哪些未完 Task/审核/待办、各自版本和 Thread sequence”，而不是把无限压缩的聊天摘要当成事实。
- Session 的换代必须由人或未来经审计 Runtime 显式触发；此切片不能声称实现了 90% 上下文阈值、自动压缩、Computer 换绑或 Claude/Codex Session resume。
- 新 Session 仍须重新读取最新 Task/Attention 后操作；Handoff Snapshot 是导航与审计，不是绕过版本/权限/freshness 的授权。

## 验收

机器规格：[team-session-continuity.schema.json](../../specs/v1/team-session-continuity.schema.json)。

测试至少覆盖：Workspace/Channel/clearance/owner 隔离、单 active Session、CAS retire、Snapshot 零正文、Task/Attention/Thread 引用范围、跨 identity/channel/已消费 Handoff 拒绝、创建时重新快照、重启、幂等、OpenAPI 和零模型/工具/自动 rotation。
