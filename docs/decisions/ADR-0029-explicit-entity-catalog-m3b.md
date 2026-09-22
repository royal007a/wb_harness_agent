# ADR-0029：以精确 Entity Catalog 衔接 M3-A 图检索

状态：Proposed（本地受限实现，HA-0033 已完成双环境验收）
日期：2026-09-20

## 背景

M3-A 的 `:graph-recall` 故意只接受已知 `entity_id`，避免服务从自然语言猜实体。但调用方若只能拿到内部 ID，显式关系链的可用性不足。已登记的 canonical name / aliases 尚未有安全的 read path。

## 决策

提供同 Bank、只读的 `:resolve-entity`：

1. 输入仅为一个完整名称、可选类型和 `as_of`；只按 casefold 后的 canonical name 或 alias 做**完全相等**匹配，不分词、模糊匹配、向量、模型或跨 Bank 查询。
2. 结果为 `resolved`（唯一）、`ambiguous`（多候选）或 `not_found`；服务绝不从多候选中自行选择。调用方必须把返回的 `entity_id` 显式交给 M3-A `:graph-recall`。
3. 候选 Entity 再次经过其 support Fact、Source、Bank、有效期和发生时间过滤；返回 Fact statement 与 Source ID/ref/SHA-256，不返回 Source 正文。
4. retract/supersede/delete 继续由 M3-A 生命周期移除/失效 Entity，因此 Catalog 不新增独立索引或删除负担。

## 后果

这只是显式 Graph API 的安全目录，不是 Entity Resolution 或自然语言 GraphQA。别名碰撞必须显示为 ambiguity；调用方只能继续澄清或选择候选 ID。需要模型消歧、跨来源合并、模糊检索或外部实体库时，必须另立 ADR、数据处理和 L3 评测。
