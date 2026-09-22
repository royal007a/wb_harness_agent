# Memory Plane M1：来源优先的长期记忆 / 知识库

状态：ADR-0026 Proposed 的本地受限实现。它是 `plan.md` 的 M1 最小可信写入与受限读回，不是完整 Hindsight、RAG、向量库、DeepAgents 集成或“记住所有聊天”。M1 之上的无模型 Context Capsule / FTS5 目录 / 按 ID 详情回读，另见 [Memory Context M2-A](MEMORY_CONTEXT_M2A.md)；以显式 Fact 支撑的至多两跳关系路径，另见 [Memory Graph M3-A](MEMORY_GRAPH_M3A.md)；用 exact canonical/alias 获取明确 Entity ID 的目录，另见 [Memory Entity Catalog M3-B](MEMORY_ENTITY_CATALOG_M3B.md)。

## 已实现的对象与生命周期

```text
Memory Bank (ws_local + local_admin + scope + classification + retention)
  └─ Source Evidence (content + source_ref + SHA-256 + time + expiry)
       └─ Fact (atomic statement + kind + confidence + valid time + state)
```

本机可信管理员显式调用 Retain，提交一份受限 Source 和 1–16 个调用方已抽取的 Fact。系统不调用模型、不从对话自动抽取、不保存 Prompt/内部推理，也不生成 Observation、Opinion 或 Mental Model。

每一条可召回 Fact 都绑定 Source、发生/记录/有效时间、分类、置信度与状态。新的事实若指定 `supersedes_fact_id`，旧事实会变为 `superseded` 而非被原地覆盖；撤回 Source 会使其 active Fact 变为 `retracted`；删除会移除 Source 正文和依赖 Fact，留下只含内容摘要与计数的 tombstone/audit。撤回、删除、幂等和所有 Bank 查询均通过 SQLite 原子事务。

## 可用 API

- `GET /api/local/memory/runtime`：M1 能力边界；明确 model extraction、Reflect、vector/graph 和 Product Task/Run 集成都为 `false`。
- `GET/POST /api/local/memory/banks`：创建/列出固定 `ws_local`、`local_admin` 的 Bank。请求不能指定所有者或工作空间。
- `POST /api/local/memory/banks/{bank_id}/retain`：显式写入 Source + Facts，需 `Idempotency-Key`。
- `POST /api/local/memory/banks/{bank_id}:recall`：返回无原始 Source 正文的 `evidence-bundle@1`。
- `POST /api/local/memory/sources/{source_id}:retract`：空 JSON + `Idempotency-Key` 撤回；`DELETE /api/local/memory/sources/{source_id}`：带 `Idempotency-Key` 删除正文/Fact 并建 tombstone。

机器契约见 [`memory-plane.schema.json`](../../specs/v1/memory-plane.schema.json)，完整 API 说明见 [API](API.md)。

## 读回规则与明确限制

M1 的 Recall 是**确定性的 read-back**，不是 M2 搜索系统：它只在指定 Bank 内过滤 active、未过保留期、有效时间命中的 Fact，再按关键词与查询时间排序。返回 Evidence Bundle 的每条 evidence 都包含 Fact、时间、状态、匹配解释和 Source 的 ID / 来源引用 / SHA-256，但不含原始 Source 正文。

M1 拒绝凭证样式内容、Restricted 数据、未知字段、Public Bank 的 Internal Source、跨 Bank supersede 和失效 Source。它也不会以“没有召回”推断“历史中没有”，更不能替代权威数据库、业务 API 或实时事实。

当前本机单用户 `ws_local` 只是功能性 bank 边界，不是生产身份或多租户授权。local audit 不是 Product Event；接入任何 Product Task/Run、Adapter、模型或外部资料前，必须单独建模身份、权限、预算、事件关联和数据外发边界。

## 时间可见性

`Recall` 的 `as_of` 不只是排序参数：只有 Source `occurred_at` 已到达该时点、其保留期仍有效、Fact active、Fact `occurred_at` 已到达且 Fact validity window 包含该时点时，Fact 才可进入关键词候选。未来记录被排除时，`empty` 仅表示截至该时点没有可读证据，不代表事实不存在。M2-A Capsule 与 detail 回读复用同一可见性规则；见 ADR-0030。
