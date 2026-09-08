# HA-0001 评审并冻结 HarnessAgent P0 规格

## 目标与非目标

目标：把抽象平台规格收敛为可验收的受控 CodeAct 数据分析 P0，统一 Task/Run、API、适配器、工具、沙箱、视觉路由和治理状态语义，并取得独立 review。

非目标：不编写运行时代码，不调用真实模型或外部系统，不批准具体基础设施采购，不宣称任何 Draft 已实现。

## 现状证据

- 三份 PDF 共 18 页已逐页渲染并 OCR，摘要见 `docs/research/SMOLAGENTS_CODEACT_SERIES.md`。
- Smolagents 的 Agent、工具/MCP 与安全执行边界已用官方文档交叉核对。
- P0、核心契约、适配器契约、沙箱边界、模型路由、JSON Schema 与 OpenAPI 已形成 Draft。
- 图片理解路由由用户指定为 `doubao-seed-2.1-turbo`，真实能力尚未探针验证。

## 变更步骤

1. 明确 P0 用户、输入、输出、非目标和固定验收夹具。
2. 分离 Harness Work Item、Product Task 与 Run 生命周期。
3. 对齐 Markdown API、JSON Schema、OpenAPI 与权限 Schema。
4. 将未经验证的 ADR 标记为 Proposed，记录 Smolagents、沙箱和视觉路由决策。
5. 运行 L0 静态验证并保存 Evidence。
6. 交由 `mymacclaude` 独立 review，记录必须修复项和建议项。
7. 用户确认 P0 与剩余决策后，才把 HA-0001 标为 completed 并移动计划。

## 风险与授权点

- 当前只修改规格和治理状态，不触发运行时代码或外部副作用。
- 不能因课程示例而把本地 Python 执行视为安全方案。
- 不能把用户指定模型等同于已证实的图片能力。
- ADR-0002 至 ADR-0008 在获得证据和确认前保持 Proposed。

## 验证矩阵

- JSON/YAML 可解析，Schema 引用存在。
- Markdown 本地链接存在，AGENTS.md 不超过 150 行。
- API 示例满足 Draft Schema，Task/Run 状态术语一致。
- 禁止把参考系统名称、未实现能力或 Proposed 决策写成当前事实。
- PDF 来源路径、页数、SHA-256、提取方法与局限已记录。
- 独立 reviewer 给出结论和可定位问题。

## 回滚方案

当前没有版本控制基线。冻结前应初始化 Git 并形成首个可审阅提交；在此之前只通过逐文件反向补丁回滚，因此这也是 HA-0001 的准入缺口。

## Evidence 位置

- `harness/evidence/HA-0001/2026-09-08-pdf-source-review.md`
- `harness/evidence/HA-0001/2026-09-08-static-validation.md`（验证后生成）
- `harness/evidence/HA-0001/2026-09-08-claude-review.md`（收到 review 后生成）

## 当前退出条件

- L0 验证无错误；
- Claude review 的必须修复项已处置或登记；
- 用户确认 P0 边界及 Proposed ADR 的下一步；
- 建立可追踪的版本控制基线。

