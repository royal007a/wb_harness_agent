# HA-0041：实现 Team Session Continuity Handoff 与有界当前工作摘要

状态：completed（2026-09-22 双环境发布）

风险：high（协作状态、引用范围与会话边界；不连接真实 Runtime 或身份）

## 目标

在 HA-0035/0036 的授权与 attention/freshness 边界之上，实现 protocol Agent 的手工 Session 生命周期和服务端生成的 Continuity Snapshot，使下一段 Session 能找到未完 Task/审核/attention 与 Thread sequence，而不复制聊天或模型上下文。

## 范围

1. 冻结 `team-session-continuity@1` Schema、ADR-0037、API/安全/架构/质量说明；
2. SQLite 保存 Team Session、创建后 Snapshot 不可改写的 Session Handoff 与一次性单调 Handoff 消费关系；
3. 按 Workspace/Channel/membership/clearance 限制创建、读取与换代；同 identity/Channel 最多一个 active Session；
4. 服务端从 Team Task/Attention/cursor 状态生成无正文、版本化的 Continuity Snapshot；
5. 新 Session 只能同 identity/scope 继承一次 Handoff，且创建时重新生成 current Snapshot；
6. 覆盖 CAS、隔离、单 active、Handoff 消费、Snapshot 引用范围、Task/attention 新鲜度不被绕过、重启、OpenAPI 与零执行合成评测；通过后按双环境规则发布。

## 非目标

- 消息/Prompt/模型上下文的保存、摘要、压缩、重放或完整历史检索；
- Provider/Runtime Session resume、token telemetry、自动 Session rotation、自动 dispatch、Daemon、Computer、工作目录/Keychain/凭据迁移；
- 修改 Task、Gate、Handoff、Attention 或绕过 ADR-0036 的 freshness；真实认证、模型、工具、网络或投研执行。

## 完成条件

- Session/Handoff/Snapshot 有机器契约，读写均通过 Workspace/Channel/membership/clearance 和 identity 所有权；
- 历史 Handoff 不能跨 identity/channel/重复消费；Snapshot 没有正文或自由文本，创建 successor 时刷新当前状态；
- 定向/全量回归、合成评测、OpenAPI、本机与远端备份/health/认证边界及无密 Evidence 完整；外部能力保持关闭。

## 完成记录

- `94cffb9` 固化机器契约、SQLite Session/Handoff、受限 API、动态 OpenAPI、定向回归和合成评测。
- 定向 Session/Attention/Task/Foundation 回归 20 passed；`tests/test_workbench.py` + Session 回归 60 passed；全量回归 244 passed、12 skipped、0 failed；`sh harness/verify.sh` 与 Session 合成评测通过。
- 本机 launchd 先完成 health、Session runtime（模型/工具均为 0）和 OpenAPI 校验；远端在独立 staging 通过编译、20 项定向回归、合成评测和 `pip check`，再由当前 systemd PID 解析实际 `HARNESS_DB`、完成在线 SQLite backup + `integrity_check` 后 promotion。
- 远端重启后 loopback health/runtime/OpenAPI、nginx 语法、服务 active 和未认证公网 401 均通过；详细无密 Evidence 见 [`harness/evidence/HA-0041/`](../../harness/evidence/HA-0041/)。
