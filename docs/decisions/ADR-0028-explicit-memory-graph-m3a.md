# ADR-0028：以显式 Entity / Relation 实现受限 M3-A 图与时间召回

状态：Proposed（本地受限实现）
日期：2026-09-20

## 背景

M1/M2-A 只能基于单条 Fact 做关键词、时间和目录详情回读。用户材料中的“小李 → 支付系统 → 风控服务 → 故障”类问题需要可追溯的关系链；仅召回相似文本不能稳定证明这条路径。

自动 NER、实体消歧、图数据库、模型抽取、向量查询和自然语言 GraphQA 都会引入新的数据外发、误归一和权限风险。目前尚未获得这些能力的批准或评测证据。

## 决策

实现 M3-A 的本机受限纵切：

1. 可信本机调用方以已有、active 的同 Bank Fact 为证据，显式创建 Entity 与 Relation；服务不读 Source 正文、不从聊天自动提取实体，也不做别名模糊匹配。
2. Entity 和 Relation 均绑定一个 support Fact，带有效时间。关系只能连接同 Bank、仍有效的 Entity；最多进行两跳 SQLite 关系遍历。
3. `:graph-recall` 只接受已知的 `start_entity_id`，重新按 Bank、来源、Fact、Entity、Relation 与时间过滤，再返回有来源引用的 `graph-evidence-bundle@1`。它不是自然语言查询、图数据库或语义检索。
4. Source retract/delete/supersede 必须使关联 Entity/Relation 不可用；删除时物理清理由已删除 Fact 唯一支撑的派生对象与关联边，且 audit/tombstone 不保留名称或来源正文。
5. 使用合成夹具验证两跳依赖影响链、时间过期、新旧关系、Bank 隔离、撤回/删除级联、环路上限、幂等与重启；默认模型、网络、Product Run/Adapter 仍关闭。

## 后果

M3-A 可以证明有限、显式的多跳 Evidence Path，但使用者必须先给出实体 ID，且同一实体的跨来源合并尚未实现。它不会宣称完成 Hindsight 的 Entity Resolution、graph retrieval ranking、自然语言问答、自动 Retain 或 Reflect。任何模型化抽取、模糊 Entity Resolution、外部图/向量服务或 Product Run 注入必须单独经过数据处理、身份/权限、成本与 L3 删除证据。
