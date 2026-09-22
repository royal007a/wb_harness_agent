# HA-0040 发布与验收记录

状态：accepted（本机受限控制面）。

## 已交付

- `team-foundation@1` 固化 Workspace、AgentIdentity、Workspace/Channel membership、`Public / Internal / Restricted` 数据等级及本机 `ws_local/local_admin` 种子。
- Team Task 升至 `team-task@2`：创建、读取、认领、Handoff、提交、Gate 和 Recovery 读写均按 Workspace、Channel、role 和 clearance 检查；旧 `team-task@1` 不会获得新身份的静默授权。
- HTTP `actor_id` 明确只是本机协议身份选择；运行时固定报告 `protocol_identity_authentication=not_connected`、外部模型调用 `0`、外部工具调用 `0`、消息交付未实现。

## 验证证据

- 定向 Team Foundation / Team Task / Recovery 回归：17 passed。
- 完整回归：235 passed、12 skipped、0 failed；见 `all-tests.xml`。
- Harness 验证和 Team Foundation 合成评测通过；隔离、clearance、Task role、legacy 不自动授权均为 1.0，模型/网络/工具执行为 0；见 `team-foundation-evaluation.json`。
- 本机 launchd 与公网 systemd/nginx 均已发布并校验 health、runtime、OpenAPI；公网未认证入口仍为 401。远端关键文件 SHA-256 与本地一致；详见 `deployment.json`。

## 发布过程修正

- 首次远端 promotion 前按默认 `.local/harness.db` 查找备份，未先解析运行服务实际的 `HARNESS_DB`；该尝试没有得到数据备份，不能倒置为“发布前备份已通过”。
- 随后已从运行中的 systemd 解析位于批准数据根目录的实际 `HARNESS_DB`，生成并完整性校验 `HA0040_20260922T042439Z.predeploy-finalization.sqlite`，再执行 exact staged source finalization restart 与 runtime 验证。`AGENTS.md` 和运维规范已固化这一步；详细时间线见 `deployment.json`。

## 不代表

真实 HTTP 身份认证、OIDC/token、Agent Runtime、Daemon/Computer、Session、Thread/DM、Inbox、work mark、freshness、模型、Provider、MCP、工具、网络或真实投研均未实现或放行。
