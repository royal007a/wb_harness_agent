# Memory Entity Catalog M3-B：精确名称到 Entity ID

状态：ADR-0029 Proposed 的本机受限实现；HA-0033 已通过完整回归、三套合成评测与本机/公网双环境发布验收。该状态不代表自动 Entity Resolution 或生产知识图谱可用。

该目录解决 M3-A 的入口问题：调用方可以用完整 canonical name 或已登记 alias 查出同 Bank 的可用 Entity 候选，再显式把 `entity_id` 传给 `:graph-recall`。它只做 casefold 的**精确相等**，不分词、不模糊、不自动选择多候选，也不使用模型、向量、网页或 Source 正文。

```text
exact name/alias → active same-Bank candidates → resolved | ambiguous | not_found
                                                   ↓ explicit ID only
                                               :graph-recall
```

`not_found` 只表示当前可访问、有效的目录没有精确名称；不代表实体不存在。`ambiguous` 必须由调用方澄清，不能静默选择一个候选。

## API 契约

`POST /api/local/memory/banks/{bank_id}:resolve-entity` 请求：

```json
{"name":"支付", "entity_type":"system", "as_of":"2026-09-20T09:00:00Z"}
```

- `name` 是必填的完整 canonical name 或已登记 alias；大小写以 Unicode `casefold` 比较。
- `entity_type` 和 `as_of` 可选。类型只是在精确候选中筛选；时间会重新验证 Source、Fact 和 Entity 的发生/有效期。
- 输入含凭证样式内容、空白、或未知字段会被拒绝。

响应状态只可能为：

- `resolved`：恰好一个候选；
- `ambiguous`：多个精确候选，调用方必须选择候选 `entity_id`；
- `not_found`：没有当前可访问且有效的精确候选，不能外推为业务实体不存在。

每个候选包含 `entity_id`、canonical name、type、实际命中的名称和 support Fact / Source ID、ref、hash、时间。随后应由调用方把明确的 `entity_id` 交给 `POST ...:graph-recall`；目录本身不执行图遍历。

## 生命周期与安全

目录不另建副本索引，而是每次读取 M3-A 的 active same-Bank Source → Fact → Entity 视图。因此 Source/Facts/Entity 的时间失效、supersede、retract、delete 会立即使候选消失；跨 Bank 也只返回空候选，不泄露名称或 ID。

目录**不**支持：自然语言分词、拼写纠正、向量/语义命中、跨来源实体合并、自动选取歧义项、模型推理、网页/PDF/聊天摄取或 Source 正文导出。它只是一条可审计的 ID 发现路径，不是 GraphQA。

机器契约见 [`memory-entity-catalog.schema.json`](../../specs/v1/memory-entity-catalog.schema.json)，静态 API 见 [`openapi.yaml`](../../specs/v1/openapi.yaml)。
