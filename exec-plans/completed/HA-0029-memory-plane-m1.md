# HA-0029：长期记忆 / 知识库 M1

## Objective

实现来源证据优先、可隔离、可撤回的最小长期记忆平面：Memory Bank、Source Evidence、Fact、审计、纠错/撤回/删除，以及不含模型的受限读回 Evidence Bundle。

## Scope

1. 定义 M1 的 bank/source/fact/retain/recall 契约和本机 policy 边界。
2. 以 SQLite canonical store 实现显式 Retain、内容去重、幂等、Fact supersede、Source retract/delete、保留期和审计。
3. 实现跨 bank 隔离与状态/有效期过滤的 keyword + temporal read-back，不返回原始 source 正文。
4. API、回归/安全测试、Evidence 和文档同步。

## Non-goals

- 不自动保存聊天、调用外部模型、从资料自动抽取、写 Observation/Opinion/Mental Model 或启动 Reflect。
- 不实现向量、BM25、图、RRF/rerank、权威 API 冲突解析、异步索引或 DeepAgents 接入。
- 不将单用户本机 bank ID 当作生产身份/租户隔离，也不将 local audit 冒充 Product Event。

## Acceptance

- 每条可召回 Fact 都绑定有效 Source、分类、时间和状态；Restricted/凭证样式内容、跨 bank、重复/漂移写入均稳定拒绝或按幂等返回。
- supersede/retract/delete 不会让失效 Fact 再被读回；delete 清除可控正文并保留无正文 tombstone/audit。
- Recall 输出受限 Evidence Bundle（无原始 Source 正文），只宣称 keyword/temporal read-back；契约、安全、重启和 API 测试有 Evidence。
