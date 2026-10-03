# HA-0052 外部 Skill 双环境受限启用

依据：用户 2026-10-03 请求，ADR-0052。范围仅外部 Skill stdlib JSON sandbox。

1. 明确 Linux Docker/Colima backend、loopback-only 执行入口及部署回滚契约。
2. 实现 backend、入口防护、有界输出与串行执行，补单元及真实容器测试。
3. 全量回归，固定 commit；本机备份和部署，再远端实际 DB 备份、staging、
   构建镜像、隔离探针、启用 systemd 配置、验证 nginx/health/执行。
4. 写双环境版本/镜像/检查/限制证据，不打开任何其他运行时门禁。

验收：两端 runtime enabled、镜像可用、真实 JSON transform/失败清理通过；
公网仅可读状态、包与执行不可访问；现有工作台正常、模型关闭。

## 执行结果（2026-10-03）

应用 `87934de` 双环境部署完成。Mac/132 的真实 Skill 套件各 17 项通过，
生产 API 的合成包执行正确并清理；公网包/执行 403，状态 401 保留认证。
已备份实际 DB 与配置；Linux 镜像的离线传输和跨架构修复有单独 provenance。
状态 waiting_approval，完整证据与已知限制在 `harness/evidence/HA-0052/`。
