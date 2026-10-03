# HA-0052 外部 Skill 双环境受限启用

依据：用户 2026-10-03 请求，ADR-0052。范围仅外部 Skill stdlib JSON sandbox。

1. 明确 Linux Docker/Colima backend、loopback-only 执行入口及部署回滚契约。
2. 实现 backend、入口防护、有界输出与串行执行，补单元及真实容器测试。
3. 全量回归，固定 commit；本机备份和部署，再远端实际 DB 备份、staging、
   构建镜像、隔离探针、启用 systemd 配置、验证 nginx/health/执行。
4. 写双环境版本/镜像/检查/限制证据，不打开任何其他运行时门禁。

验收：两端 runtime enabled、镜像可用、真实 JSON transform/失败清理通过；
公网仅可读状态、包与执行不可访问；现有工作台正常、模型关闭。
