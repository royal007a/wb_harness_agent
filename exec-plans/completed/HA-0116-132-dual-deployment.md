# HA-0116：132 客服与 DSH 双服务发布

用户于 2026-10-07 明确要求两版都部署。属于运维发布，不合并两条分支。

## 规格与范围

- 客服继续使用 /opt/harnessagent、harnessagent.service、127.0.0.1:8765 和 /harness/support，保留实际 HARNESS_DB、加密凭证和知识库。发布 561a605（运行代码与已验收 7eaf317 相同）。
- DSH 固定已验收 da43bff，独立 /opt/harnessagent-dsh、harnessagent-dsh.service、127.0.0.1:8876、/var/lib/harnessagent-dsh。独立域名 dsh.118.196.123.132.nip.io，通过现有 nginx Basic 认证和 HTTPS；HTTP 重定向 HTTPS。沿用现有证书，不声称公开 CA 信任。
- 独立 staging 预检、备份实际客服数据库与应用、失败恢复应用和服务；不复制本机数据库、Keychain、运行历史或凭证，不修改其他服务。
- DSH真实Provider保持未准入，除非远端已有被授权、可解析的独立凭证。验收合成Provider的真实DSH工具链，不冒称真实模型验收。

## 验收

1. 本机客服8765和DSH8876版本健康可读；服务器两个进程分别健康、端口仅loopback。
2. 客服原有Provider/会话/知识库不丢失，发布版本正确；备份可读取且SQLite完整性通过。
3. DSH依赖检查、运行创建、终态、账本归零、事件及产物摘要验证通过；重启后Run仍存在。
4. 两个公网入口未认证401、认证成功，静态资源和浏览器无脚本错误；DSH新入口不影响客服旧入口。
5. 归档固定版本、备份路径、验证范围及真实模型未启用限制；不重跑无关全量门禁。

## 状态

completed；两个入口、合成运行、重启持久化与客服数据保留均通过。证据：harness/evidence/HA-0116/acceptance.md。DSH真实Provider未准入。
