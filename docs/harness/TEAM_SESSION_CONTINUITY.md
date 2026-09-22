# Team Session Continuity：有界当前工作摘要与手工换代（ADR-0037）

## 范围

`team-session-continuity@1` 是 Team 协作控制面的导航和交接层，不是模型/Provider Session，也不是消息系统。它不保存、压缩或重放聊天正文；它只将下一段工作所需的已验证状态组织为有界 Snapshot。

| 对象 | 回答的问题 | 保存 | 不保存 |
|---|---|---|---|
| Team Session | 当前 protocol identity 在哪个 Channel 上有一段协作 Session | identity / Workspace / Channel / lifecycle / version | 模型上下文、Prompt、消息、目录、凭据 |
| Session Handoff | 旧 Session 给下一段的审计起点 | reason、不可改写的 Snapshot、一次性消费关联 | 自由文本总结、内部推理、工具输出 |
| Continuity Snapshot | 下一段首先应检查什么 | Task/Attention ID、版本、状态、Thread/read sequence | Task 目标、Handoff 正文、附件、消息正文 |

## 手工状态流

```text
create --> active --handoff(CAS)--> retired
                                  |
                                  +--> one same-identity successor inherits Handoff and receives a newly generated snapshot
```

- 同一 protocol identity 在同一 Channel 最多一个 active Session；这不限制它持有的 Team Task lease 或 Attention lease。
- `handoff` 由服务端读取当前可见的 Task、Gate、Attention 和 cursor 生成 Snapshot，再 retire 旧 Session；不能用客户端摘要覆盖事实。
- successor 只能消费同 Workspace / Channel / identity 的未消费 Handoff，并在创建时重新生成 current Snapshot。历史 Snapshot 不等于当前状态，也不能绕过 ADR-0036 的 Task freshness；Handoff 唯一的后续变化是由 `null` 单调写成 successor ID 的消费审计关联。
- 没有已连接 Runtime telemetry 时，`manual_handoff`、`local_maintenance`、`session_reset` 都只是显式受限原因；没有自动 context 压缩、90% 阈值、自动 resume 或自动 rotation。

## Snapshot 语义

`current_task` 仅在有且只有一项身份持有有效 Task execution lease 时设置。其余开放 Task 分别出现在 `owned_tasks`、`pending_reviews`、`available_tasks`。`attention_items` 只列该 identity 尚未清除的 item ID 和状态；`thread_freshness` 给出该 identity 的 read sequence 与当前 latest sequence。

Snapshot 仅作导航：执行者仍需用 Team Task 详情、Attention Inbox 和当前 read cursor 重读后再交接、提交或 Gate。

## API

| 方法 | 端点 | 用途 |
|---|---|---|
| GET | `/api/local/team/sessions/runtime` | 声明本机、无 Runtime telemetry/模型/工具/自动 rotation 的边界 |
| GET / POST | `/api/local/team/sessions` | 列出 identity 自己的 Session / 创建一个 active 或继承 Session |
| GET | `/api/local/team/sessions/{session_id}?actor_id=...` | 读取 Session、当前生成的 Snapshot 与可见 inherited Handoff |
| POST | `/api/local/team/sessions/{session_id}:handoff` | CAS 生成 Handoff、retire 当前 Session；不执行或派发任何工作 |

所有写请求使用 `Idempotency-Key`，并拒绝未知字段和凭证样式内容。完整机器契约见 [`team-session-continuity.schema.json`](../../specs/v1/team-session-continuity.schema.json)。

## 边界

- `actor_id` 是 ADR-0035 的 protocol identity，不是登录 principal。
- 本模块不读任何 Agent Lab/Agent Runtime chat Session，也不导入 Memory Source 或外部链接。
- Computer 换绑、Keychain/工作目录迁移、Provider Session resume、上下文利用率和自动 compaction 必须另行设计并经过 L3 认证/遥测/数据审查。
