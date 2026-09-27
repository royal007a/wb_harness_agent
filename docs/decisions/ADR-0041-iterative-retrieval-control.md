# ADR-0041：以证据缺口驱动的迭代式检索控制

## 状态

Proposed（设计适配，未启用语义/外部检索）

## 背景

重复上一轮 Query 只能反复召回相似内容，不能证明答案在推进。复杂问题需要把每轮检索看成一次“补齐证据缺口”的动作，并保留可审计的检索轨迹。该决策把课程中的迭代式检索、混合召回和 Agentic RAG 适配到本项目已有的 Memory/Evidence/Gap/预算边界。

## 决策

1. **以 Evidence Gap 驱动下一轮**：每轮结束必须产出已确认事实、未覆盖缺口、继续理由和下一轮目标；下一轮 Query 必须至少改变实体、关键词、时间/版本条件、数据源或验证方向之一。规范化为 Unicode NFKC + casefold，按 Unicode 字母/数字连续段切词（中文术语由调用方提供已分词项），各集合排序去重；`query_key` 是规范化 `query_terms + entity_ids + time/version filters + source_ids + methods + support_or_contradict` 的 SHA-256，并由固定测试向量锁定。key 相同，或词集合 Jaccard ≥ 0.85 且过滤条件相同，重复 Query 默认拒绝，只有显式 `rerun_reason` 才可递增 `attempt` 重跑。
2. **统一候选到 Evidence Bundle**：向量、关键词、图、时间、多源 API 的结果先归一为带 `evidence_id`、`source_ref`、时间、来源可信度和内容摘要的证据候选，再做硬条件过滤、去重、冲突标记和排序。原始 Source 正文不进入 Bundle。
3. **增量合并而非覆盖**：同一 evidence 去重；高度相似结果降低 novelty；新旧冲突保留双方及 `supersedes/retract` 状态；权威源优先级只能由已登记 source policy 决定，不能由模型临时改写。
4. **排序加入信息增益**：字符 3-gram Jaccard ≥ 0.80 视为近似重复；`novelty=1-max(similarity_to_existing)`，不再用 gap 数二次修正。当前 SourcePolicy 没有 trust 字段，固定 `source_trust_mode=unavailable`，排序不使用可信度。多路 `normalized_rank = rank / max(1,list_length)`，取同一候选跨方法的最小值；采用 `uncovered_gap_count desc → novelty desc → normalized_rank asc → source_ref asc → evidence_id asc` 的固定字典序，已覆盖证据不占满后续预算。
5. **效果与资源双停止**：默认 `max_rounds=3`；有效新增定义为不重复、不近似重复且至少覆盖 1 个 open Gap 的 evidence，单轮少于 2 条算无进展，连续两轮停止；重复率 ≥ 0.80 停止；每个关键 Claim 至少 1 条允许来源证据才算充分。另受时间/Token/工具/费用预算、数据源耗尽和不可检索缺口约束。停止原因必须写入 Retrieval State。
6. **分阶段实现**：先在本机确定性 FTS5、时间过滤、显式 Graph 和 Evidence Bundle 上实现控制器；语义向量、RRF、reranker、外部资料和模型化 Query Expansion 仍受 ADR-0031 Admission Gate 约束，默认关闭。

## Retrieval State（规范字段）

每个检索 Run 持久化：`session_id`、`round`、`query`/`query_delta`、`query_key`、`source_ids`、`methods`、候选 evidence（带 ID、source_ref、摘要、rank、novelty、gap_ids）、`new_evidence_ids`、`confirmed_fact_ids`、`open_gap_ids`、`continue_reason`、`next_round_goal`、`attempt`、`rerun_reason`、`coverage_delta`、`duplicate_rate`、每轮实际 `elapsed_ms/token_count/tool_calls/cost_minor` 和 `stop_reason`。机器结构见 `specs/v1/retrieval-state.schema.json`。状态只保存受控元数据与证据引用，不保存原始聊天、凭证或未授权 Source 正文。

## 评测

离线评测至少报告 Recall@K、Precision@K、MRR、NDCG、Evidence Coverage、Duplicate Rate、Conflict Resolution Accuracy、平均轮数/延迟/成本，以及“修改成本”：漏召回、错误召回、重复和排序错误分别计为新增、删除、合并和移动操作数。评测集必须包含多轮缺口补齐、时间变化、冲突来源、不可检索缺口和提示注入样例。

## 边界

迭代式检索不是自动事实裁决，也不把“没有召回”解释为“事实不存在”。Agentic RAG 只有在每轮工具、来源、权限、预算和停止条件均受控制时才可接入；任何没有来源证据的结论仍标记为未评估。
