# HA-0030：同步部署 HA-0028 / HA-0029 到本机与公网

## Objective

将已验收的外部 Skill 隔离运行时与 Memory Plane M1 部署到既有本机 launchd 和 `118.196.123.132` systemd/nginx，并将双环境部署作为项目硬规则固化。

## Scope

1. 在 AGENTS/Operations 记录每次可部署实现变更均需先本机、再远端验证的规则。
2. 验证本机服务加载 HA-0028/0029 runtime 路由且外部 Skill gate 仍关闭。
3. 远端备份 SQLite，安全同步工作树/requirements/deploy 文件，重启 systemd 与 nginx，验证健康、认证代理、新端点和默认门禁。
4. 保存不含凭证的部署 Evidence；失败时保留备份与稳定错误，不伪造部署成功。

## Non-goals

- 不启用外部 Skill 执行、模型、外部资料、Claude L3、memory 自动抽取或任何新凭证。
- 不迁移本机 SQLite/Keychain/测试数据到远端，不修改 nginx Basic Auth 口令或远端安全策略。

## Acceptance

- 双环境规则进入 AGENTS 和 Operations，明确例外与无密约束。
- 本机与远端均返回外部 Skill/M1 runtime，远端代理认证仍有效且两项高风险 gate 保持默认状态。
- 远端有部署前数据库备份、systemd/nginx 健康检查、版本/端点 Evidence；测试或同步失败时能定位并不覆盖备份。

## Result

Completed on 2026-09-19. The local launchd service and the remote `systemd`/nginx mirror both serve HA-0028/HA-0029 runtime endpoints. The remote SQLite backup was created before synchronization; systemd is active, nginx validation passed, and unauthenticated access to the public proxy is still rejected with `401`. Both high-risk runtime gates remain off. See `harness/evidence/HA-0030/`.
