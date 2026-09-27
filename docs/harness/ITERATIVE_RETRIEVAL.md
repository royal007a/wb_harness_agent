# 迭代式检索适配说明

## 一句话

把“再查一轮”改成“针对一个明确 Evidence Gap 补证据”，并把每轮查询、结果、增量、冲突、预算和停止原因写入可审计 Retrieval State。

## 与当前 Harness 的对应关系

| 课程概念 | 当前承载 | 适配原则 |
|---|---|---|
| Query 变体 | Retrieval State 的 `query_delta` | 必须新增实体、关键词、时间/版本、验证方向或数据源 |
| 多路/多源召回 | Memory M1/M2-A/M3-A 的受限 read path | 先统一 Evidence Bundle，再过滤、去重、融合 |
| 缺失信息 | Gap State | Gap 是待补证据，不是“答案为否” |
| 新旧冲突 | Fact lineage / `supersedes` / `retract` | 保留证据链，不原地覆盖 |
| 细节召回 | M2-A `:recall-details` | 只按已返回的 evidence ID 精确回读 |
| 关系检索 | M3-A `:graph-recall` | 只从显式 entity ID 出发，最多两跳 |
| 停止条件 | Run budget + Retrieval State | 效果条件与资源条件任一触发即可停止 |
| Agentic RAG | 未来 M2-B/M4 | 受 ADR-0031 Admission Gate，默认关闭 |

## 一轮控制流程

```text
读取当前 Evidence Bundle / open Gaps
  → 生成非重复 query_delta（规则优先）
  → 按权限和 source policy 选择方法/数据源
  → 候选召回与硬过滤
  → evidence 归一、去重、冲突标记、novelty/gap coverage 排序
  → 增量合并并更新事实与缺口
  → 评估停止条件；继续则记录下一轮目标，否则记录 stop_reason
```

## Query 生成规则

优先采用确定性补充：第一轮出现的新术语作为关键词；为实体增加时间、版本、用户或范围条件；围绕当前结论查询支持证据与反证；切换到尚未查询且允许的数据源。规范化先做 Unicode NFKC、casefold，再按 Unicode 字母/数字连续段切词；中文词由调用方提供已分词术语，词、实体、过滤器、source、method 均排序去重。`query_key` 是规范化的 `query_terms + entity_ids + time/version filters + source_ids + methods + support_or_contradict` 的 SHA-256；实现必须保留固定测试向量。key 相同，或词集合 Jaccard ≥ 0.85 且过滤条件相同，判为重复；只有瞬时失败、来源刷新或明确重试策略才能重跑，并递增 `attempt`、记录 `rerun_reason`。

## 合并与排序

候选先用稳定 `evidence_id/source_ref` 去重，再按规范化文本的字符 3-gram Jaccard 识别高度相似项；Jaccard ≥ 0.80 视为近似重复，保留较早 rank，另一项 `novelty=0`。`novelty = 1 - max(similarity_to_existing)`；`uncovered_gap_count` 单独作为排序信号，不重复修正 novelty。当前 source policy 没有可信度/优先级字段，因此 `source_trust_mode=unavailable`，排序不使用可信度，不能暗示来源等级。排序采用固定字典序：`uncovered_gap_count desc → novelty desc → normalized_rank asc → source_ref asc → evidence_id asc`；不比较异构原始分数，平局按稳定 ID 打破。多路结果的 `normalized_rank` 是各路候选在该轮的 `rank / max(1, list_length)`，取候选在所有命中方法中的最小值。冲突不静默择一：保留两条证据、记录来源与时间，并交给 Fact lineage 或人工 Gate。

## 停止与交接

默认控制参数固定为：`max_rounds=3`；每轮有效新增必须是“不重复、不近似重复且至少覆盖 1 个 open Gap”的 evidence，少于 2 条视为无进展；连续两轮无进展则 `no_progress` 停止；候选重复率 ≥ 0.80 则 `duplicate_rate` 停止；每个关键 Claim 至少需要 1 条允许来源证据才算 `evidence_sufficient`。另受每 Run 的时间、Token、工具调用和费用上限约束。最小回答原则不等于少查证据：关键 Claim 覆盖不足时必须保持 `open_gap` 或转澄清。停止前写入 `stop_reason`；转人工时提交 Evidence Bundle、open Gaps 和下一步建议，不自动扩大权限。

## 评测门槛

除 Recall@K、Precision@K、MRR、NDCG 外，必须报告 Evidence Coverage、Duplicate Rate、Conflict Resolution Accuracy、平均轮数/延迟/费用和修改成本。修改成本按 `miss*3 + wrong*2 + duplicate*1 + kendall_adjacent_swaps*1` 除以 `max(K,1)` 归一；NDCG 使用固定标注等级（3=直接支持关键 Claim，2=部分支持，1=背景相关，0=无关）；冲突裁决准确率以人工标注的有效时间、来源类型和 supersede/retract 状态为金标准。所有迭代结果必须与同一数据集、同一 K 的单轮基线并列，报告新增轮数、延迟和费用。评测要覆盖“重复 Query”“新术语补查”“反证查询”“时间冲突”“无法检索”和提示注入。没有这些证据，不得把 Agentic RAG 标记为 available。

## 当前实现状态

本文件是设计适配。当前已实现的是 M1 确定性关键词/时间读回、M2-A Fact Capsule/按 ID 详情和 M3-A 显式图路径；尚未启用 embedding、RRF、reranker、自动 Query Expansion、外部多源检索或模型化 Reflect。
