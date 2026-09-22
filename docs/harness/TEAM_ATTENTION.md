# Team Attention：Inbox、work mark、执行租约与 freshness（ADR-0036）

## 范围

`team-attention@1` 不是消息系统或 Agent Runtime。它只把已授权 Workspace/Channel 上的协作提示表示为不含正文的 `source_ref + sequence`，并将“读过”和“还欠动作”分开持久化。

| 对象 | 回答的问题 | 保存 | 不保存 |
|---|---|---|---|
| Conversation | 这个 Thread 最新到哪一条协议提示 | Workspace/Channel/Thread、latest sequence | 消息正文、附件、模型上下文 |
| Attention item | 谁需要注意什么类型的提示 | source ref、作者/目标、种类、优先级、状态 | 消息内容、Prompt、工具输出 |
| Read cursor | 该协议身份读到哪里 | agent/thread/read sequence | “已处理”结论 |
| Work mark | 是否仍欠一个动作 | item/agent/open/in-progress/cleared | Agent 内部思考 |
| Attention lease | 当前谁在处理哪一件思考工作 | item/agent/expiry | Runtime/模型会话 |

## 状态与优先级

服务端固定 `human_correction=100`、`direct_mention=80`、`task_review=60`、`subscription_update=40`。Inbox 只展示目标 Agent 仍有权限读取的 Item，并按 priority、sequence 排序。

```text
pending --claim--> in_progress --complete(fresh)--> completed
   ^                    |
   +---- release/expire-+
```

- `read cursor` 更新不清除 work mark；lease 过期只释放 Item，work mark 回到 `open`。
- 一个 Agent 一次只可持有一个 active Attention lease；这不改变它已持有的 Team Task execution lease。
- item completion 需要 item version、active lease 和最新 read cursor 同时匹配；最新 sequence 已变化时不能以旧稿完成。

## Freshness 与 Task

当 Team Task 所属 Thread 已有 Attention sequence：

1. 执行者或 reviewer 先读取并提交当前 `read_sequence`；
2. Handoff、submit、Gate 请求携带 `freshness.read_sequence`；
3. 服务端在写入同一个 SQLite transaction 内比对 cursor、expected value 与 Conversation `latest_sequence`；
4. 若期间出现新提示，返回 `TEAM_FRESHNESS_REQUIRED`，调用方补读后决定改写、继续或停止。

没有 Attention sequence 的 Thread 维持既有 Team Task 兼容路径；它不是绕过新鲜度，而是没有可比较的协议消息。

## API

| 方法 | 端点 | 用途 |
|---|---|---|
| GET | `/api/local/team/attention/runtime` | 明示手工 ingress、无自动 dispatch、无 Runtime/模型/工具 |
| GET | `/api/local/team/inbox?actor_id=...` | 只列出该 identity 可见的 attention/work mark 元数据 |
| POST | `/api/local/team/attention/items` | 手工登记 opaque source ref，服务端生成 sequence/priority/work mark |
| POST | `/api/local/team/attention/items/{item_id}:claim` | 领取一件思考工作，建立单 Agent Attention lease |
| POST | `/api/local/team/attention/items/{item_id}:release` | 放弃本次领取，work mark 回到 open |
| POST | `/api/local/team/attention/items/{item_id}:complete` | 仅在 lease/version/read sequence 均新鲜时完成并清除 mark |
| POST | `/api/local/team/channels/{channel_id}/threads/{thread_id}:read` | 写入当前 identity 已读到的 latest sequence |

所有写请求使用 `Idempotency-Key`；请求和响应拒绝凭证样式内容及未知字段。当前不提供消息内容、线程浏览、通知、DM、自动唤醒或对外发送。

## 边界

- `actor_id` / target identity 都只是本机 protocol identity，不是 token/OIDC/签名会话。
- Item 的 `source_ref` 是不透明的非 URL 引用（例如 `source:message-42`），不能承载消息正文、附件 URL、Prompt、token 或工具结果。
- `manual_protocol_ingest_only` 不代表已接入飞书、Slack、Email 或任意消息产品。
- 当前没有模型、Provider、工具、网络、Agent Runtime、Daemon、Computer、自动委派或自动审批。
