# ADR-0030：统一 Memory 读路径的发生时间过滤

状态：Proposed（本地受限实现，HA-0034 已完成双环境验收）
日期：2026-09-20

## 背景

M1 `:recall`、M2-A `:context` 与 `:recall-details` 已检查 Bank、active status、有效期和来源保留期；M3-A 的图路径还检查了 Source/Fact/Entity/Relation 的发生时间。但前三条读路径没有在所有层级一致排除相对 `as_of` 尚未发生的 Source 或 Fact。这样会让“历史某个时点”查询看到未来证据，且不能将其误称为 temporal recall。

## 决策

1. 所有 Source-backed Fact 读路径以同一个 `as_of` point 对 Source 的 `occurred_at` 和 Fact 的 `occurred_at` / `valid_from` / `valid_to` 过滤；未来 Source 或 Fact 不可见。
2. `:recall`、`:context`、`:recall-details` 对同一 Bank / 时间点应有一致的可见事实集合；FTS5 仍只是可重建候选索引，不能绕过规范文档过滤。
3. 无可见证据仍返回现有 `empty` / unavailable 语义；不把时间过滤解释为事实不存在或索引故障。
4. 该切片不引入 embedding、RRF、reranker、缓存、自动摘要、模型或外部数据。真正 M2-B 语义/融合检索仍须经过版本化语料、数据处理、模型/embedding、性能成本和 L3 审批。

## 后果

该变更收紧历史查询，而不改变当前时点的已发生、有效事实。新增回归和合成评测必须覆盖 future Source、future Fact、细节回读、跨 Bank、重启和无原始 Source 正文；按双环境规则发布。
