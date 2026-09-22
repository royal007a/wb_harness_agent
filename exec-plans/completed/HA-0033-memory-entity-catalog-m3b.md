# HA-0033：实现 Memory Entity Catalog M3-B

## Objective

为 M3-A 的显式 Graph API 提供可追溯、无模型、无模糊匹配的同 Bank exact Entity catalog，使调用方不必手工保存内部 Entity ID。

## Scope

1. 先定义 ADR-0029、机器 Schema、OpenAPI/API/安全/质量文档和 Work Item。
2. 实现 `:resolve-entity`：canonical name/alias 的 casefold 精确匹配、Entity/Fact/Source/时间/Bank 重验证和 resolved/ambiguous/not_found 结果。
3. 覆盖别名、同名歧义、类型筛选、跨 Bank、retract/delete/supersede/时间、敏感/未知字段、重启和合成评测。
4. 通过完整回归、本机与公网双环境的备份、健康、OpenAPI/新增端点和默认门禁 Evidence。

## Non-goals

- 模糊/向量/语义匹配、模型 Entity Resolution、跨来源合并、自动选择歧义候选或自然语言 GraphQA。
- 自动资料摄取、模型/网络、Product Run/Adapter 接入和多租户身份。

## Acceptance

- Catalog 只返回 active 同 Bank、有效、来源可追溯的候选，原始 Source 正文和跨 Bank 名称零泄漏；歧义必须保留而非猜测。
- 生命周期/时间、别名和拒绝反例的测试/合成评测通过，且不把 not_found 解释为实体不存在。
- 本机/远端双环境部署及所有新端点/认证边界验证通过，外部能力保持关闭。
