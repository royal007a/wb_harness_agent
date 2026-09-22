# HA-0038：实现 Team Attention Inbox、work mark、执行租约与 freshness

状态：completed

风险：high（协作状态、数据隔离和过期结论阻断；不连接真实身份或执行）

## 目标

在 ADR-0035 Workspace/Channel 数据边界之上实现一段本机、可审计的 attention control plane：手工协议 ingress、目标身份 Inbox、独立 work mark、单身份 attention lease 和 sequence freshness，并把 freshness 接入 Team Task 的 Handoff、submit 与 Gate 写路径。

## 范围

1. 冻结 `team-attention@1` Schema、ADR-0036、API/安全/架构/质量说明；
2. SQLite 保存 Conversation sequence、Attention item、Read cursor、Work mark 与 Attention lease；
3. 以 Workspace/Channel/membership/clearance 过滤 ingress、Inbox、读游标和操作；
4. 每个 Agent 同时最多一个 attention lease；到期只释放领取，不丢失 work mark；
5. 在 Task Handoff、submit、Gate 的同一事务中验证 Thread freshness；
6. 覆盖隔离、优先级、无正文、幂等、单 lease、到期、过期稿拒绝、重启、OpenAPI 和零执行合成评测；通过后发布本机与 `118.196.123.132` 并保留无密 Evidence。

## 非目标

- HTTP 登录、token/OIDC、真实用户或 Agent 认证、消息正文/附件/Thread/DM 存储、飞书/Slack/Email 接入、WebSocket、通知、自动 dispatch、自动委派；
- Agent Runtime、Provider、模型、MCP、工具、网络、Keychain、Computer、Session 或真实工作目录；
- 以 Inbox 状态替代 Team Task Handoff/Gate，或把 protocol `actor_id` 写成生产身份授权。

## 验收与发布记录（2026-09-22）

- 所有 Attention/read cursor/work mark/lease/freshness 路径均受 Workspace/Channel/membership/clearance 约束；schema、静态/运行时 OpenAPI 与重启持久化均有测试。
- 单 identity lease、到期 work mark 保留，以及新 sequence 对 completion/Handoff/submit/Gate 的阻断均有正反例；完整回归为 240 passed、12 skipped、0 failed，合成评测通过。
- 本机 launchd 和远端 systemd/nginx 已发布并验证 health、runtime、OpenAPI、实际数据库的 promotion 前 online backup、nginx、服务 active 与公网未认证 401。完整无密 Evidence 见 `harness/evidence/HA-0038/`。
- 远端未安装 `sqlite3` CLI；该首次备份命令在 promotion 前失败且没有改动运行系统，随后使用 Python 标准库 SQLite online-backup 加完整性检查完成同一要求。此项过程修正已写入 Evidence。
