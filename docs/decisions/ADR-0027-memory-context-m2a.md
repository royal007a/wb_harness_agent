# ADR-0027：以显式 Fact Capsule 实现 M2-A 上下文压缩与按需详情召回

状态：Proposed（本地受限实现）
日期：2026-09-20

## 背景

M1 已证明 Source/Fact 的可追溯、撤回与删除，但只做遍历式 keyword/temporal read-back。它不会自动保存对话，也没有“当前 K 轮原文 + 压缩摘要 + 精确详情”的上下文管理能力。用户提供的长任务材料强调：摘要必然有信息损失，真正可靠的机制必须让模型能用目录找到细节，并让最终结论回到证据。

官方 Hindsight 资料把 Retain / Recall / Reflect、Memory Bank、事实/经验/Observation 和多策略检索作为独立能力；这为目标架构提供研究线索，但不等于本项目应引入其运行时或把其性能主张当作项目结果。来源：[Hindsight 官方仓库](https://github.com/vectorize-io/hindsight)、[开发者检索说明](https://github.com/vectorize-io/hindsight/blob/main/skills/hindsight-docs/references/developer/index.md)、[ACL Demo 论文](https://aclanthology.org/2026.acl-demo.27/)。

## 决策

实现本机、无模型的 M2-A，而不是伪造自动摘要或语义向量检索：

1. 继续由可信调用方显式 Retain Source 与 Fact。Fact 的短 `statement` 是模型可读的受控摘要；可选 `detail` 是同一来源的有界细节，普通 Recall 不返回它。
2. `:context` 接受调用方暂时提供的最近不超过 8 轮原文（不写库），以 SQLite FTS5 从同一 Bank 选出有效 Fact，返回结构化 Fact Capsule、目录和允许精确读取的 evidence ID。它不生成自然语言摘要、不保存会话、不访问模型或外网。
3. `:recall-details` 只接受目录中已有的 Fact ID，重新做 Bank / 来源状态 / 有效期过滤后，返回所选 Fact detail 与来源引用；原始 Source 正文永不返回。
4. FTS5 只是可从 canonical Fact 重建的本地关键词索引。source delete 物理清除细节和索引项；retract/supersede/过期在读时过滤。索引损坏或无候选不能表达为“历史不存在”。
5. 以合成评测集衡量关键 Fact 命中、摘要保真、精确详情、冲突/撤回安全和跨 Bank 零泄漏；不把它称为语义 Recall、RRF、rerank、Hindsight 或真实模型质量。

## 后果

M2-A 能提供“近 K 轮由调用方持有 + 已授权历史的摘要目录 + 按 ID 回读细节”的可审计纵切，但仍无自动对话摄取、模型摘要、向量/图/语义检索、RRF/reranker、缓存、权威源冲突裁决、身份/租户或 Product Run 接入。它不会将任何上下文或 detail 自动发送给模型；未来接入模型还需独立的数据最小化、权限、预算与 L3 证据。
