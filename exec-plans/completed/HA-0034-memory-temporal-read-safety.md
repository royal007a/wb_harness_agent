# HA-0034：统一 M1/M2 Memory 发生时间读取安全

## Objective

让 `:recall`、`:context`、`:recall-details` 与 M3-A 一样，只返回在 `as_of` 已发生、来源有效、Fact active 且有效期匹配的同 Bank 证据。

## Scope

1. 用 ADR-0030 与机器/接口文档固化 Source/Fact `occurred_at`、Fact validity 与 `as_of` 的一致语义。
2. 收敛三个读路径到同一活动 Source/Fact 过滤，不让 FTS5 候选绕过它。
3. 为 future Source / future Fact、历史 detail、Bank 隔离、retract/delete/restart 添加回归与合成评测。
4. 全量验证并先部署本机、再部署公网；记录备份、端点和仍关闭的外部能力。

## Non-goals

- embedding/semantic/vector、RRF/rerank、缓存、自动摘要、模型、自动摄取、GraphQA 或 Product Run 接入。
- 改变已发布 M3-A/M3-B 的 Entity/Relation / exact Catalog 匹配规则。

## Acceptance

- 三条 Source-backed Fact 读路径在相同 Bank/`as_of` 下不泄露未来 Source 或 future Fact，且依旧不输出原始 Source 正文。
- 索引/生命周期/隔离/重启反例、合成评测和全量回归通过。
- 本机与公网均经可恢复 SQLite 备份和新旧接口/认证边界检查；模型/外部能力保持关闭。
