# Memory Context M2-A：结构化摘要与按需详情召回

状态：ADR-0027 Proposed 的本机受限实现。它扩展 M1 的可追溯 Fact，而不是替代 M1、自动记录聊天或开放外部 RAG。

## 问题与边界

上下文压缩必然损失信息。因此 M2-A 不把一段自由文本摘要当作唯一记忆，而将每个可注入的摘要条目绑定到原子 Fact 与 Source。短 `statement` 用于 Capsule，独立的有界 `detail` 只在模型/调用方从目录选择对应 evidence ID 后返回。原始 Source 正文不出现在 Capsule、Detail Bundle、Event、SSE 或 Evidence。

当前 K 轮原文由调用方暂时传入 `:context`，只原样回到该响应，绝不写入 Memory 数据库。它让未来的 Agent Runtime 可以把尚未索引的近期信息与长期 Fact 并列处理，而不把现有 Session 自动变成长期记忆。

## 两阶段调用

```text
调用方持有的最近 K 轮（transient） ───────────────┐
                                                   ▼
POST :context → FTS5 候选 + 时间/状态过滤 → Fact Capsule + Detail Catalog
                                                        │
                                 模型/调用方声明缺口并选择 evidence ID
                                                        ▼
POST :recall-details → 重新验证有效性 → Detail Bundle + Source 引用
```

- `POST /api/local/memory/banks/{bankId}:context`：返回 `memory-context-capsule@1`。摘要为 `fact-derived-summary@1`，明示 `is_model_generated=false`；其分组固定为 objective、entity、fact、constraint、preference、decision、state。
- `POST /api/local/memory/banks/{bankId}:recall-details`：最多取 8 个目录 Fact。撤回、过期、跨 Bank、删除或无效的 ID 不泄漏正文，列入不可用集合；Detail Bundle 仍不含原始 Source content。

## 当前能力和非能力

已实现：SQLite FTS5 keyword index、时间/状态/Bank 过滤、摘要目录、精确详情、删除传播、重启重建和合成评测。评测只使用临时 SQLite 中的 synthetic Source/Fact；2026-09-20 的最新全量 opt-in 回归为 223 passed（一个上游 Starlette 弃用警告），不能将该结果外推为真实模型或线上召回质量。

明确未实现：语义 embedding、向量、RRF、reranker、缓存、自动/模型摘要、自动对话写入、真实模型注入、Reflect、多租户身份和 Product Task/Run 关联。ADR-0028 的 M3-A 另行实现**显式**的两跳 relation 路径，ADR-0029 的 M3-B 仅补充 canonical/alias 精确的 Entity ID 目录；它们不改变本页的 FTS5 关键词语义，也不提供自动实体消歧或自然语言 GraphQA。FTS 命中只代表字词匹配，不代表语义理解。

ADR-0031 已将后续 M2-B semantic/vector/RRF 的准入固定为机器 Gate：当前 `not_admitted`、runtime disabled、模型/外部调用为 0。变为 admitted 前必须有版本化去标识语料、数据外发、删除/重建、离线相关性和成本/延迟 Evidence；变为 admitted 后仍不等于已接入或上线。

## 评测

评测集必须使用合成去标识 Source，分别测量：关键 Fact hit/precision、摘要中目标/约束/决策/状态的保真、目录到 Detail 的精确读取、supersede/retract/delete 后的不召回、跨 Bank 零泄漏、最近轮不落盘、索引重建与安全拒绝。任何语义或最终回答质量指标都等待后续 M2-B 的真实受控模型/embedding 基线。

## 时间可见性

Capsule 目录和按 ID detail 都会再次按 `as_of` 验证 Source `occurred_at`、Source 保留期、Fact active status、Fact `occurred_at` 与 Fact validity window。因未来/失效/跨 Bank 而不可读的 detail 只进入 `unavailable_evidence_ids`，不会把未来 detail 或原始 Source 正文带回上下文。FTS5 只能缩小候选，不能绕过该过滤；见 ADR-0030。
