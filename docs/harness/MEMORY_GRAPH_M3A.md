# Memory Graph M3-A：显式关系链与时间召回

状态：ADR-0028 Proposed 的本机受限实现。2026-09-20 已通过合成关系链/时间/删除评测、215 项全量 opt-in 回归与双环境发布验证；此证据不外推为自动 GraphQA 或生产知识图谱质量。

M3-A 解决的是“关系链是否有证据”，不是让模型猜关系。它只接受调用方在已 Retain 的同 Bank active Fact 上显式登记 Entity / Relation；每个对象均绑定 support Fact 和有效时间。调用方使用已知 `entity_id` 调用 `:graph-recall`，服务最多作两跳遍历并返回每一条边的 Fact/Source 引用。若调用方只有 canonical name/alias，可先使用 M3-B 的 [Memory Entity Catalog](MEMORY_ENTITY_CATALOG_M3B.md) 获取零、一个或多个明确候选；歧义不得在服务端自动选择。

```text
Source → Fact ──support──> Entity
                  └─support──> Relation(Entity → Entity)

known start_entity_id → status/time/Bank filters → at most two hops → evidence paths
```

此路径不会：读取原始 Source 正文、自动解析聊天/PDF/文件、按名称模糊查人、调用模型或 embedding、访问网络、写 Product Task/Run，或把无路径解释为“没有影响”。Source retract/supersede 会使依赖证据失效；delete 会清理仅由已删 Fact 支撑的派生 Entity/Relation。它仍不是完整图数据库、Hindsight 集成、实体消歧或 Reflect。
