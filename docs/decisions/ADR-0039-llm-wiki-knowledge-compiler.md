# ADR-0039：以 LLM-Wiki 作为可审计的知识编译层

状态：Proposed  
日期：2026-09-23

## 背景

普通 RAG 适合对静态资料做一次性相似检索，但不能自然表达页面状态、实体关系、来源演化、冲突和持续维护。长期记忆又需要保留 Source Evidence、Fact lineage 与权限边界。若直接把原始资料或模型摘要灌入向量库，会造成重复处理、来源丢失、过期结论污染和难以审计。

## 决策

在 P2 设计中引入一个 **LLM-Wiki 知识编译层**，采用 `raw/`、`wiki/`、`schema/` 三层模型：

- raw 保存不可变来源或带 digest 的来源指针；
- wiki 保存经过 schema 编译的 Markdown 页面、稳定 ID、链接和状态；
- schema 规定页面格式、状态迁移、来源覆盖、链接完整性和维护 Gate；
- `index.md` 与追加式 `log.md` 是可重建的导航和审计投影；
- Wiki 页面可被 RAG/Memory Recall 作为受控适配器读取，但不能替代权威数据库、业务 API、普通 RAG 或 Memory Policy Gateway；
- 模型生成的候选事实、摘要和关系默认为派生内容，必须保留 source_refs 并通过 Gate 才能进入 accepted 或 Canonical Memory。

## 后果

正面影响：

- 人类与 Agent 都能直接阅读、审查和 Git diff；
- 新资料在已有页面和链接上增量生长，减少重复读取；
- 页面、来源、schema、编译器版本和审核结果可重建、可回滚、可审计；
- 普通 RAG、Memory Recall 和 Wiki 查询可以按任务路由，而不是强制一条主链路。

约束与代价：

- 需要维护 schema、链接、冲突和 stale 页面，不能把 Markdown 当成自动正确；
- raw、wiki、索引、缓存和派生 Memory 的删除/撤回必须级联；
- accepted 页面之前需要来源覆盖、权限、数据分类和人工/程序 Gate；
- 本 ADR 不授权 Provider、网络、Keychain、模型抽取或生产写入；这些仍由既有 admission contract 单独控制。

## 非目标

- 不在本 ADR 中实现向量数据库、语义 RAG、自动实体消歧或 Reflect；
- 不把 Wiki 页面宣称为当前已经实现的运行时能力；
- 不把外部资料中的提示词、代码或链接视为 HarnessAgent 的控制指令。

## 验收方向

W0/W1 先以 Public PDF、网页和冲突更新夹具验证：schema/链接/来源覆盖、增量 diff、supersede/retract、`index.md`/`log.md` 重建、越权拒绝和 Git 回滚。通过后再讨论受控模型抽取与 Recall 接入。
