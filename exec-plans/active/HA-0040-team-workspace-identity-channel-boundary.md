# HA-0040：Workspace、Agent Identity 与 Channel 授权数据边界

状态：running

风险：high（协作身份/隔离语义；不涉及真实认证或外部执行）

## 目标

在 HA-0037 Team Task 与 HA-0039 Recovery Guard 之前新增一个可持久、可验证的本机协议身份和 Channel access boundary，使 Task 不再把任意 `actor_id` 当成已授权身份。

## 范围

1. 冻结 `team-foundation@1` Schema、ADR-0035、API/安全/架构说明；
2. SQLite 持久化 Workspace、Agent Identity、Workspace membership、Channel、Channel membership 及安全的 `ws_local/local_admin` 种子；
3. 以 data class、membership 和 Channel role 限制 Team Task v2 的创建、读、认领、交接、提交和 Gate；
4. 旧 `team-task@1` 保留但不自动暴露/授权；
5. 覆盖隔离、角色、clearance、幂等、重启、OpenAPI、零执行状态的测试；通过后部署本机和 118.196.123.132 并保留无密 Evidence。

## 非目标

- 不实现 HTTP 登录、token/OIDC、真实 Agent/人身份认证、跨设备会话、Daemon、Computer、Workspace 消息/Thread/DM、Inbox、work mark、freshness 或自动委派；
- 不复制或迁移 Keychain、Provider session、工作目录、私有 memory、消息正文、模型推理或工具输出；
- 不开启模型、Provider、MCP、外部工具、网络、真实投研或任何权限副作用；
- 不把 protocol identity 描述为生产级身份认证或多租户授权。

## 完成条件

- Workspace / Channel / membership 和 data-class 数据边界均由机器契约验证；
- Team Task v2 的各读写路径在 membership/role/clearance 不满足时稳定拒绝，Gate reviewer 仍需 task-level 一致；
- legacy Task 不被静默扩权；完整回归、OpenAPI、本机/远端备份发布、health、认证边界和新增端点验证通过；
- Evidence 说明外部能力仍关闭。
