# HA-0041 发布与验收记录

状态：accepted（本机受限 Team Session 控制面）。

## 已交付

- `team-session-continuity@1` 固化 Team Session、CAS 手工 Handoff、一次性同 Workspace/Channel/identity 继承以及有界 Continuity Snapshot。
- Snapshot 只可从当前有权限的 Team Task、Gate、Attention 和 read cursor 派生 Task/Attention ID、版本、状态和 Thread sequence；不复制 Task 目标、Handoff 正文、消息、Prompt、附件、模型上下文或 Provider Session。
- 每个 identity/Channel 最多一个 active Session；handoff retire predecessor，successor 的创建会刷新 current Snapshot。历史 Handoff 只作审计导航，不能越过 Task/Attention 的 owner、CAS 或 freshness。
- SQLite 表、API、动态 OpenAPI、重启、幂等、隔离和合成评测均已覆盖；运行时固定不连接 Agent Runtime/telemetry，外部模型/工具调用为 0。

## 验证证据

- Session/Attention/Task/Foundation 定向回归：20 passed；Workbench + Session 回归：60 passed。
- 全量回归：244 passed、12 skipped、0 failed；见 `all-tests.xml`。
- Harness 验证和 Team Session 合成评测通过：metadata-only Snapshot、单 active、一次性 Handoff、fresh successor Snapshot 与零外部执行均为 1.0；见 `team-session-continuity-evaluation.json`。
- 本机 launchd 与公网 systemd/nginx 均已发布并校验 health、Session runtime、OpenAPI；远端当前运行服务的实际 SQLite 已在 promotion 前在线备份并完成完整性检查；远端关键实现 SHA-256 与本地一致；公网未认证入口仍为 401。详见 `deployment.json`。

## 不代表

HTTP 身份认证、OIDC/token、真实 Agent identity、消息/Thread/DM 正文、Provider/模型 Session resume、上下文压缩、Daemon/Computer、自动 rotation/dispatch、模型、Provider、MCP、工具、网络或真实投研均未实现或放行。
