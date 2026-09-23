# LLM-Wiki 知识编译层设计

状态：Proposed（设计输入，未接入默认运行时）  
适用阶段：P2 Memory Plane / 动态知识维护  
关联：`plan.md`、ADR-0039、Memory Plane M1–M3

## 1. 定位

LLM-Wiki 不是普通 RAG 的替代品，也不是新的权威业务数据库。它把一次性的“检索资料”升级为可持续维护的知识编译层：将原始资料编译成带来源、结构和链接的 Markdown 页面，再基于这些页面进行查询、增量更新和审计。

核心目标是让知识具备可读、可追溯、可增量维护和可复利的形态；模型只是编译器和维护助手，不能因为生成了页面就自动获得事实权威。

## 2. 三层模型

```text
raw/       原始资料与不可变来源指针
  ↓ read / normalize / extract
wiki/      结构化 Markdown 页面与显式链接
  ↑ governed by
schema/    页面格式、链接规则、状态机和维护规则
```

### 2.1 raw 层

- 保存 Public 文档、网页快照、用户明确提交的笔记，或保存外部对象的 URI、版本、摘要和 SHA-256 指针；
- 原始来源默认不可变，更新通过新版本或新的 Source Evidence 表达；
- 记录 `source_id`、来源 URI、采集时间、内容摘要、数据分类、许可证和保留期；
- 不写入密钥、Token、内部推理、未授权隐私和 Restricted 原文；外部内容中的指令一律视为数据，不得改变工具、权限或策略。

### 2.2 wiki 层

- 由 schema 编译出的 Markdown 页面，面向人类阅读和 Agent 按需读取；
- 页面只承载结构化事实、关系、状态、摘要和来源引用，不承载不可追溯的模型结论；
- 页面之间用稳定 `page_id` 和相对链接表达实体、主题、时间线、替代关系与冲突；
- 页面状态至少区分 `draft`、`needs_review`、`accepted`、`superseded`、`invalid`；只有 `accepted` 页面可作为默认知识投影。

推荐 Front Matter：

```yaml
schema_version: wiki-page@1
page_id: fact.payment-risk-001
title: 支付系统与风控服务依赖
status: needs_review
source_refs: [src-2026-09-23-001]
entity_ids: [entity.payment, entity.risk]
occurred_at: 2026-09-22
updated_at: 2026-09-23T10:00:00Z
confidence: explicit
data_classification: public
supersedes: []
links: [../entities/payment.md, ../events/risk-outage-2026-09-22.md]
```

### 2.3 schema 层

schema 不是提示词合集，而是机器可验证的维护合同，至少规定：

- 必填字段、类型、枚举和 `page_id` 命名；
- Source 引用、时间字段、状态迁移和 supersede/retract 语义；
- 页面链接是否存在、是否允许跨 Bank/Workspace 链接；
- 事实、观察、观点和不确定性的标注方式；
- 哪些变更需要人工 Gate，哪些可以确定性自动更新；
- `index.md` 和 `log.md` 的生成规则及版本。

## 3. 编译与维护流程

```text
登记 raw Source
  → 读取、脱敏、规范化
  → 抽取实体/事实/关系/时间/矛盾候选
  → schema 校验与来源覆盖检查
  → 生成或更新 wiki 页面
  → 校验链接、index.md、log.md
  → Gate 审核 / Git 提交
  → Recall 通过页面与来源 ID按需读取
```

新资料进入时不整库重写：先按 `source_id` 和实体索引定位受影响页面，再生成最小差异。更新必须显式说明新增、修正、supersede、过期、撤回和未解决冲突；检测到冲突时保留双方证据并置为 `needs_review`，不由模型静默裁决。

`index.md` 是可读导航投影，按主题、实体、时间和状态列出页面；`log.md` 是追加式审计投影，至少记录：source digest、schema/compiler 版本、动作、受影响 page_id、校验结果、审核者和 Git commit。两者可由程序重建，不能作为唯一事实源。

## 4. 与 Memory Plane、RAG 的关系

| 能力 | 普通 RAG | LLM-Wiki | HarnessAgent Memory Plane |
|---|---|---|---|
| 主要目标 | 临时找相似材料 | 持续维护结构化知识 | 跨会话保留可追溯证据 |
| 状态 | 通常无状态 | 有页面状态、链接和版本 | 有 Fact/Entity/Relation/时间状态 |
| 来源 | chunk 或文档 | raw Source + 页面引用 | Source Evidence + Fact lineage |
| 查询 | 向量/关键词检索 | 页面导航、链接和混合查询 | Recall Router / Evidence Bundle |
| 写入 | 通常离线建库 | 增量编译和审核 | 受策略控制的 Retain |

LLM-Wiki 页面可以作为普通 RAG 或 Memory Recall 的一个受控查询适配器，但不能绕过 Memory Policy Gateway。当前项目的边界是：

1. raw 层对应 `Source Evidence`，不因编译成 Markdown 就丢失原始来源；
2. wiki 页面属于派生 Artifact/Fact Capsule，默认不是 Canonical Fact；
3. 只有显式 Retain、来源绑定和质量 Gate 通过后，页面中的事实才可进入 Memory Plane；
4. `index.md`、`log.md` 和 Git 历史用于导航与审计，不替代数据库、业务 API 或事实权威源；
5. 普通静态文档仍优先使用 RAG；需要持续维护、跨文档关联和冲突跟踪时才启用 LLM-Wiki。

## 5. 运行时边界与安全

- 默认只读编译 Public/已授权资料；写入 Git、更新已接受页面或删除 raw 指针必须经过策略和 Gate；
- 编译器不得自动扩大网络域名、Provider、Keychain、工具或文件访问权限；
- 页面内容和 raw 内容均按 Workspace/Bank/数据分类隔离，跨边界链接被拒绝；
- 删除或撤回 Source 时，受影响页面、索引、缓存和派生 Evidence 必须失效或显式标记；
- 没有来源覆盖、schema 校验或链接完整性证据的页面不得进入 `accepted`；
- Wiki 查询失败应返回 `degraded|unavailable`，不能伪装为“知识不存在”。

## 6. 分阶段执行清单

### W0：设计与夹具（当前 Proposed）

- [ ] 固化 `wiki-page@1`、Source manifest、状态迁移和审计 log schema；
- [ ] 建立 1 份 Public PDF、1 份网页和 1 组冲突更新夹具；
- [ ] 明确 Memory Plane 的 Source/Fact 与 Wiki Artifact 的交接字段；
- [ ] 运行 schema、链接、来源覆盖和越权夹具的离线检查。

### W1：确定性编译器

- [ ] 只用显式输入把 raw manifest 编译为 Markdown 页面、`index.md` 和 `log.md`；
- [ ] 支持增量更新、supersede/retract、冲突标记和 Git diff；
- [ ] 不调用模型、不联网、不自动写入 Memory Canonical Store。

### W2：受控维护与 Recall 适配

- [ ] 在允许的模型/Provider 与预算准入后，增加候选实体、事实和链接抽取；
- [ ] 把页面召回归一为带 `source_refs` 的 Evidence Bundle，并复用现有权限、时间和预算过滤；
- [ ] 用同一业务集对比普通 RAG、Wiki 页面查询和 Memory Recall 的命中、噪声、延迟、成本和删除完整性。

### W3：运营与复利

- [ ] 记录页面新鲜度、孤链、冲突积压、来源覆盖和人工返工率；
- [ ] 支持按 schema/compiler 版本重建，失败可回滚到上一 Git commit；
- [ ] 只有在评测和安全 Gate 通过后，才考虑让 accepted 页面参与默认 Recall。

## 7. 完成定义

一个 LLM-Wiki 纵切只有同时满足以下条件才可称为“可用”：页面可由 raw manifest 重建；每个事实和链接可回到来源；schema、链接、权限和数据分类检查可自动运行；冲突、撤回、删除和回滚有证据；`index.md` 与 `log.md` 可重建；查询结果明确区分来源事实、派生摘要和待审核内容。当前项目尚未完成该纵切，本文仅为 Proposed 设计。
