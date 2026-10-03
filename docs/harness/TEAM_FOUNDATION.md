# Workspace、Agent Identity 与 Channel 数据边界（ADR-0035）

## 当前能力与诚实边界

`team_foundation_boundary@1` 为 Team Task 的本机控制面补上五种持久对象：Workspace、Agent Identity、Workspace membership、Channel、Channel membership。它让 Task 的 `workspace_id`、`channel_id` 和 `actor_id` 具备可检查的**协议授权**含义。

它不是登录系统，也不是运行中的 Agent Team：HTTP 中的 `actor_id` 尚未由 token、签名会话或外部 IdP 解析；模型、工具、消息、Inbox、Daemon、Computer、私有 memory 与工作目录均未连接。Runtime 必须固定报告：

```text
protocol_identity_authentication = not_connected
agent_runtime                    = not_connected
external_model_calls             = 0
external_tool_calls              = 0
message_delivery                 = not_implemented
```

## 授权模型

| 对象 | 保存内容 | 不保存内容 |
|---|---|---|
| Workspace | 名称、数据等级、状态、创建者 | 业务事实、凭据、消息正文 |
| Agent Identity | 协议 ID、`human/agent`、显示名称、状态 | Provider/模型绑定、token、Keychain、工作目录 |
| Workspace membership | `owner/admin/member`、clearance、状态 | 真实登录凭据 |
| Channel | 所属 Workspace、标题、数据等级、状态 | Thread、消息、私有上下文 |
| Channel membership | `coordinator/contributor/reviewer/observer`、状态 | 注意力、Inbox、执行租约 |

访问 Channel 或其 Team Task 的前置条件是：Agent identity active、Workspace membership active、clearance 不低于 Channel 数据等级，且 Channel membership active。权限不满足时不返回 Channel 的 Task/Handoff/Gate 内容。

| 操作 | 最小 Channel role |
|---|---|
| 读取 Task/Channel | 任意 active Channel membership |
| 创建 Task | coordinator |
| claim、Handoff、submit | contributor 或 coordinator |
| Gate decision | reviewer 或 coordinator，且仍必须等于 Task 预设 reviewer |

Workspace owner/admin 才能创建 Agent、成员或 Channel，以及授予 Channel roles。创建 Channel 的管理者自动获得 coordinator。

HA-0059 明确列表与详情共享当前 Channel 可见边界：归档、membership撤销或
clearance不足的Channel不得继续通过列表泄露ID/标题。身份目录仍是Workspace
管理元数据，不承诺目标身份可调度；本项不增加认证或在线撤销API。
HTTP验收见 [Team读可见性](../../specs/testing/TEAM_READ_VISIBILITY.md)。

HA-0063 在读取Foundation行时增加结构/类型/枚举与SQL主键、关联键检查。
损坏记录返回固定500/TEAM_STATE_CORRUPT，不再按撤销/归档静默隐藏，也不自动
迁移或改数据；合法suspended/archived/revoked保留原有拒绝和目录语义。Channel
列表改用共享(code,status)白名单。检查不是全库扫描、时间真实性验证或新身份认证；
详见 [持久记录完整性](../../specs/testing/TEAM_STATE_INTEGRITY.md)。
HA-0064使25个Team/Recovery写入口在旧幂等键命中后重新检查当前资格；允许读取的
仍是历史收据，不重做状态转换、租约、过期回收或预算消耗。见
[回放授权](../../specs/testing/TEAM_REPLAY_AUTHORIZATION.md)。本机与132尚未发布此修复。

## Team Task v2 与历史记录

新建 Task 固化 `workspace_id`、`channel_id`、`created_by_id`。`team-task@2` 的授权检查发生在 create、read、claim、handoff、submit、close 和 Gate 前；Recovery Guard 通过既有 Task claim 检查一并受约束。

旧 `team-task@1` 和关联 Recovery 记录不删改、不自动给旧 actor 建身份或 membership。它们被标为 legacy-unbound，新的 protocol 身份不可读取或操作；由 `local_admin` 走显式迁移/审计流程之前，系统不能假设旧 ID 等价于新身份。

## API

所有写接口都要求 `Idempotency-Key`，所有请求拒绝 credential-shaped 元数据。

| 方法 | 端点 | 用途 |
|---|---|---|
| GET | `/api/local/team/foundation/runtime` | 返回协议身份/外部能力的关闭状态 |
| GET / POST | `/api/local/team/workspaces` | 按 actor 可见列出 / 由 `local_admin` 建 Workspace |
| GET | `/api/local/team/workspaces/{workspace_id}?actor_id=...` | 授权读取 Workspace 与其 memberships |
| POST | `/api/local/team/workspaces/{workspace_id}/agents` | 管理员创建 Agent Identity，并授予 member |
| GET | `/api/local/team/workspaces/{workspace_id}/agents?actor_id=...` | 授权列出该 Workspace Agent |
| POST | `/api/local/team/workspaces/{workspace_id}/memberships` | 管理员添加已有 Agent |
| GET / POST | `/api/local/team/workspaces/{workspace_id}/channels` | 授权列出 / 管理员创建 Channel |
| GET | `/api/local/team/channels/{channel_id}?actor_id=...` | 授权读取 Channel / members |
| POST | `/api/local/team/channels/{channel_id}/memberships` | 管理员授予 Channel roles |

Task 列表和详情需要 `actor_id` query；Task 创建改为显式携带 `workspace_id` 与 `creator_id`。此 ID 是本机协议身份，不是公网身份认证证明。

## 后续边界

1. 用户重新开启 HA-0038 后，才能以 Channel membership 作为 Inbox、work mark、execution lease 与 freshness 的过滤前提。
2. Computer / Session Handoff 还需独立 Session、设备归属、凭据不迁移和 Runtime telemetry 规格。
3. 真实投研 Agent 仍需 L3 Provider/联网/真实资料源/外发/成本/审计探针；不能由本 ADR 放行。
