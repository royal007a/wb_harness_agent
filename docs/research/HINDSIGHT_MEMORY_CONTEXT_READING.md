# Hindsight 与上下文压缩 / 细节召回阅读总结

日期：2026-09-20
用途：为 HarnessAgent 的 Memory Context M2-A 设计输入；不是 Hindsight 已被接入或其 benchmark 已被本项目复现的声明。

## 已核验的来源

1. [Vectorize Hindsight 官方仓库](https://github.com/vectorize-io/hindsight)：说明其 Memory Bank、world/experience/observation/mental model、Retain/Recall/Reflect，以及向量、关键词、实体关系和时间表示。
2. [官方开发者检索说明](https://github.com/vectorize-io/hindsight/blob/main/skills/hindsight-docs/references/developer/index.md)：说明 Semantic、Keyword、Graph、Temporal 四条检索路径、RRF 和 cross-encoder 的目标边界。
3. [ACL 2026 System Demonstration](https://aclanthology.org/2026.acl-demo.27/)：论文摘要说明 Retain/Recall/Reflect 与并行 vector/keyword/graph/temporal pipeline；这些是论文/系统的报告结果，不外推为 HarnessAgent 的运行结果。

## 阅读结论

### 1. 摘要不是“更多历史文本”

长上下文的核心矛盾不是有没有历史，而是 token 预算有限、历史中有噪声、偏好和决策会过期、最终结论必须可回到证据。整体摘要、章节摘要、工具结果摘要与关键事实的职责不同；任何压缩都会损失信息，因此摘要不能成为唯一事实源。

对 HarnessAgent 而言，模型可读摘要应是受控对象：最少包括目标、实体、事实、约束、偏好、决策、状态和来源 ID。它必须标明是“Fact-derived”还是模型生成；后者不能静默覆盖前者。

### 2. 细节召回必须有证据路径

成熟方案不让模型只看到一段不可解释的摘要。先给受控目录/摘要，模型或调用方指出缺口，再用查询、实体、时间或目录 ID 取得细节。返回应包含事实、时间、状态、来源和匹配说明；最终推断与证据分开存放。

Hindsight 的完整设计使用 Semantic、Keyword、Graph、Temporal 并行检索，经 RRF 与交叉编码器重排。该设计说明“单一向量 Top-K 不够”，但并不意味着每个系统都应一次性启用所有通道：必须根据任务、数据权限、延迟和预算分阶段验证。

### 3. 冲突与删除比召回更基础

新偏好不应原地覆盖旧偏好；应保留版本链，通过 supersede、retract、有效期和来源可信度表达变化。删除或撤回必须使规范事实、索引、缓存和派生结论失效。无召回只能表示“当前通道没有可用证据”，绝不能表示“历史中不存在该事实”。

### 4. 评测要分开量化每一层

至少需要：关键事实 Recall/Precision、摘要保真、冲突裁决、证据覆盖、跨 Bank 泄漏、删除完整性、索引新鲜度、P95 延迟/成本和降级正确性。最终回答质量需要独立、有来源的任务集；不能拿论文分数或一个 API 成功响应替代项目内基线。

## 对当前项目的落地

M1 已有 Source/Fact、时间、状态、supersede/retract/delete 和确定性 read-back。M2-A 只实现安全的第一步：调用方临时保留最近 K 轮、Fact-derived Capsule、SQLite FTS5 关键词目录和按 evidence ID 精确 Detail。它不自动写聊天，不调用模型，不返回原始 Source，不声称语义检索。

后续 M2-B 才应在完成嵌入模型/数据处理审批、版本化语料、隐私评审、索引重建、性能成本和离线评测后，增加真正的语义检索与混合融合。M3/M4 再分别处理实体图/权威冲突和受控 Reflect。
