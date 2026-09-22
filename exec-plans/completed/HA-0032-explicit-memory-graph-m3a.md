# HA-0032：实现显式 Memory Graph M3-A

状态：已完成。2026-09-20 已通过 215 项全量 opt-in 回归、M2-A/M3-A 合成评测、本机 launchd 与公网 systemd/nginx 部署验证；Evidence 位于 `harness/evidence/HA-0032/`。

## Objective

在 M1/M2-A 的 Source-first Memory Plane 上实现没有模型、没有外部数据的 Entity / Relation / temporal 两跳 Evidence Path，解决可审计依赖影响链的最小纵切。

## Scope

1. 先落 ADR-0028、独立 Graph Schema、OpenAPI/API/架构/安全/质量文档和 Work Item。
2. 新增 canonical SQLite Entity/Relation 表及显式登记接口；每个对象绑定有效同 Bank Fact，拒绝跨 Bank、失效/撤回支撑、循环和未知字段。
3. 实现有界两跳 `:graph-recall`，返回不含 Source 正文、每条边带 Fact/Source 引用的 Graph Evidence Bundle；把 retract/delete/supersede 的失效/清理传播纳入事务。
4. 以合成依赖链、时间、新旧关系、隔离、删除、重启与降级反例评测；通过本机和远端双环境发布、备份、健康与新增端点验证。

## Non-goals

- 模型/规则自动 Entity Extraction、Entity Resolution、别名模糊搜索、自然语言 GraphQA、embedding/vector、RRF/rerank、Reflect 或外部图服务。
- 自动摄取飞书、文件、PDF、网盘、浏览器/互联网，或向模型发送 Entity/Relation/Graph Evidence。
- 多用户身份/租户、Product Task/Run 关联和把“无路径”解释成权威无影响结论。

## Acceptance

- 所有 Node/Edge 都只能来自 active、同 Bank、有效 Fact/Source；Graph Bundle 不含 raw Source，跨 Bank/过期/撤回/删除绝不泄漏名称或证据。
- 至多两跳的合成多跳、关系更新和删除/重启/幂等/循环反例通过；无路径和索引/数据异常有稳定、诚实的结果。
- 相关 L2/L3 质量门禁、无密 Evidence、local launchd 与 `118.196.123.132` systemd/nginx 的备份/健康/新增端点检查均通过，模型和外部能力仍关闭。
