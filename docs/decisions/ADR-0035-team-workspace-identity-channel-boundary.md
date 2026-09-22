# ADR-0035：先冻结 Workspace、Agent 身份与 Channel 数据边界

状态：Proposed（本机受限实现）

日期：2026-09-22

## 背景

ADR-0033 已实现 `Team Task → Handoff → Gate`，ADR-0034 已实现恢复的受限决策旁路，但两者中的 `actor_id`、`workspace_id`、`channel_id` 仍只是本机协议字段。若直接在此基础上增加 Inbox、消息或执行租约，任何能够猜到 ID 的调用方都可能被误认为同一协作者，且 Channel 无法成为数据隔离边界。

用户要求先补齐 Workspace、Agent 身份和 Channel 的授权/数据边界；Inbox、work mark、freshness、Daemon 和真实 Agent Runtime 继续等待后续单独准入。

## 决定

新增独立 `team-foundation-boundary@1` 本机控制面：

- 持久化 `Workspace`、`AgentIdentity`、`WorkspaceMembership`、`Channel` 与 `ChannelMembership`。AgentIdentity 只描述协议身份和显示名称，不绑定 Provider、模型、凭据、工作目录或 Computer。
- 每个 Workspace 与 Channel 固定 `Public / Internal / Restricted` 数据等级；成员必须同时具备 active Workspace membership、满足数据等级的 clearance 和 active Channel membership 才能读取或操作该 Channel 的 Team Task。
- Workspace 的 `owner/admin` 可以创建 Channel、创建/加入 Agent 身份和授予 Channel role；创建 Channel 的管理员自动获得 `coordinator`。Channel role 明确限制为 `coordinator`、`contributor`、`reviewer`、`observer`。
- 新的 Team Task 升为 `team-task@2`，在创建时固化 `workspace_id` 与 `created_by_id`，并要求 Channel `coordinator` 创建；`claim/handoff/submit` 需要 `contributor` 或 `coordinator`，Gate 需要 `reviewer` 或 `coordinator`。`scope` 仍不是工具权限。
- 默认种子仅有本机 `ws_local` 和 `local_admin`。HTTP 调用中携带的 `actor_id` 只是在本机可信边界内选择协议身份：不提供登录、令牌签名、外部用户认证、SAML/OIDC、跨设备会话或权限执行。运行时必须明确报告 `protocol_identity_authentication=not_connected`。
- 旧的 `team-task@1`、相关 Recovery Case 保留在 SQLite 中，但不自动映射到新的身份或 Channel membership；对它们的读写返回稳定的 legacy-unbound 错误。这比静默给历史 ID 授权更安全。

## 后果

- 后续 Inbox、work mark、freshness 和消息可建立在可验证的 Workspace/Channel access set 上，而不是把每个 `actor_id` 当身份事实。
- 现有 Team Task 需要以 `team-task@2` 新建；调用方必须先显式建成员和 Channel。这是刻意的 compatibility boundary，不是数据删除或静默迁移。
- 本切片不存消息正文、Thread、私有 Agent memory、模型推理、工具输出、Keychain 内容或工作目录，也不启动模型、工具、Daemon、WebSocket、自动委派或自动审批。
- 不构成真实用户/Agent 身份认证或多租户生产授权；任何公网、跨设备或外部 IdP 使用仍须独立的 L3 身份、会话、审计与渗透验证。

## 验收

机器规格：[team-foundation.schema.json](../../specs/v1/team-foundation.schema.json)。

测试必须覆盖：种子边界、Workspace admin 管理、数据等级/Workspace/Channel 隔离、Channel role 拒绝、Team Task 操作授权、旧 Task 不自动暴露、幂等性、重启持久化、OpenAPI 一致性与零模型/工具/消息交付状态。发布仍需本机和公网双环境 Evidence。
