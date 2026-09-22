# ADR-0036：以受限 Attention Inbox 补齐已读、待跟进、租约与新鲜度

状态：Proposed（本机受限实现）

日期：2026-09-22

## 背景

ADR-0035 已让 Workspace、Channel、成员、数据等级和角色成为可检查的协议边界。若下一步直接把每个 Channel 更新自动唤醒 Agent，既会把闲聊和中间过程塞入上下文，也会让同一身份并发产生互不知情的结论；若只记录未读，又无法说明某件事是否仍欠一个动作。

用户要求把 Inbox、work mark、execution lease 与 freshness 做成下一段协作闭环，同时维持当前无登录、无消息传输、无 Agent Runtime、无模型/工具执行的边界。

## 决定

新增独立的 `local_team_attention@1` 控制面，只保存协作所需的**元数据**：

- `Conversation` 按 `workspace_id + channel_id + thread_id` 保存单调 `latest_sequence`；不保存消息正文或附件。
- 人或协议调用方用手工 `attention item` ingress 登记一个 `source_ref`、作者、目标协议身份和类型。`human_correction / direct_mention / task_review / subscription_update` 的优先级由服务端固定，不接受调用方提交 priority 或正文。
- 每个 Item 同时有独立 `work mark`。Read cursor 回答“我读到哪里”，work mark 回答“我是否仍欠一个动作”；claim 时 mark 为 `in_progress`，release/租约到期回到 `open`，完成后才 `cleared`。
- 每个协议 Agent 同时最多拥有一个未过期 Attention execution lease。SQLite 事务及 `agent_id` 唯一索引阻止并行领取；lease 到期不清除 work mark，避免下一次把未完事项误判为已处理。
- Agent 必须先对 Conversation 写入自己实际观察到的 `read_sequence`，才能完成 Item。完成动作、Team Task Handoff、submit 与 Gate 若该 Thread 已有 attention sequence，必须在**同一 SQLite 事务**中校验 caller cursor 与 `expected read_sequence` 都等于当前 latest sequence；不满足时返回稳定 `TEAM_FRESHNESS_REQUIRED`，不写入过期结论。
- 人类纠正只是一种最高优先级的手工协议 Item；没有自动唤醒、队列 worker、WebSocket、消息发送或 Agent Run。`actor_id` 仍不是登录身份。

## 后果

- Team Task 的既有执行 lease 管理“谁可修改这项交付”；Attention lease 管理“同一协议身份当前可处理哪一件思考工作”。二者不能互相替代。
- 由于还没有真实 Channel/Thread 消息服务，本切片只接收 opaque `source_ref` 与 sequence，不能宣称实现了飞书/Slack/DM、自动消息合并、真实 Agent 调度、消息内容检索或已认证身份。
- 未来 Runtime 可以把实际受授权消息转换为本契约中的 ingress；在独立身份、传输审计、保留期、限流和 L3 验证通过前，不能启用自动 dispatch 或让外部调用方伪装人类纠正。

## 验收

机器规格：[team-attention.schema.json](../../specs/v1/team-attention.schema.json)。

测试至少覆盖：Workspace/Channel/clearance 隔离、opaque source 无正文、server-derived priority、read 与 work mark 分离、单 Agent 单 lease、过期 lease 的 mark 保留、同 Thread sequence 合并、freshness 阻断 completion/Handoff/submit/Gate、乐观版本/幂等/重启、零模型/零工具/零自动 dispatch、OpenAPI 与双环境发布 Evidence。
