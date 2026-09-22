# ADR-0032：以 Fact Lineage 解释新旧结论的纠正链

状态：Proposed（本地受限实现，HA-0036 已完成双环境发布）
日期：2026-09-20

## 背景

当前 Memory Plane 已用 `supersedes_fact_id` / `superseded_by_fact_id` 保存纠正关系：新 Fact 不会原地覆盖旧 Fact，普通 Recall 只返回 active、当前有效的 Fact。这个规则能避免过期结论影响当前回答，但在需要解释“为什么从上午偏好改为下午”“哪条事实替换了旧决策”时，调用方无法获得有界、可审计的证据链。

## 决策

未来新增只读 `:fact-lineage`，**以已知 Fact ID 为入口**，返回至多固定长度的同 Bank supersede 前后链：

```text
current Fact ←supersedes— previous Fact ←supersedes— older Fact
```

每一项必须带 Fact 状态、发生/有效时间、纠正方向和 Source ID/ref/SHA-256；不返回 Source 正文，不按自然语言猜 Fact，不跨 Bank，不把 superseded Fact 当作当前结论。查询时还应区分：

- **lineage history**：允许显示可追溯的 superseded 历史以解释变化；
- **current applicability**：仅 active、Source 未撤回且满足 `as_of` 的节点可标为当前有效；
- **unavailable**：删除、跨 Bank、无关 ID 或过长链不能泄露对象存在性。

## 后果

这是一条 Evidence State / temporal correction 的解释接口，不是自动冲突裁决、Observation、Opinion、Reflect、自然语言问答或完整审计查询。实现前需确定删除 tombstone 是否可参与 lineage、max depth、同一 Fact 多重替代的拒绝语义，以及用户/租户身份后的权限模型。
