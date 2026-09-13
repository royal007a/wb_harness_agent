# 本地意图契约与规则路由（P1 受限切片）

状态：HA-0013 已验收。此切片为本地 CSV 工作台增加“提交前理解”，不接入模型、向量库、长期记忆或自动选引擎。

## 目标

把用户自然语言目标与已选择资源预检为 `intent-contract@1`：识别唯一支持的 `local_csv_analysis` 意图，校验 `analysis_goal` 与 `resource_id` 两个必填槽位，返回缺槽澄清或明确拒识，并给出可解释的固定路由。只有用户随后显式提交，工作台才创建 Product Task；预检绝不执行 Run。

## 契约与边界

- 机器契约：`specs/v1/intent-contract.schema.json`。
- API：`POST /api/local/intents:interpret`，输入仅含 `objective` 和可选 `resource_id`；响应不回显目标原文，只返回长度与 SHA-256 摘要。
- `ready`：规则识别为本地 CSV 分析，两个槽位满足，路由固定为 `engine_mock_analytics`，且标记 `explicit_user_submit`。
- `clarification_required`：已识别分析意图但缺 CSV 资源；响应给出一个固定、可操作的问题。
- `rejected`：空目标或不属于本地 CSV 分析的输入；不猜测其他业务流、不创建 Task、不调用模型。
- `confidence` 仅为 `deterministic/rules@1`，不是统计概率；不存在模型置信度伪装。

硬约束为“已登记 CSV 资源”和“仅本地执行”。规则命中、槽位状态、约束状态与路由版本均返回 `reason_codes`，便于审计和回放。

## 规则与评测

规则只在目标包含分析动作，且目标带数据语义或已选择 CSV 时识别；关键词不命中、闲聊、网盘下载和其他业务请求一律拒识。规则表、评测器和固定样例是同一版本，评测不读取生产 Task/Run。

评测夹具位于 `fixtures/intent-evaluation-v1.json`，覆盖：可执行分析、缺资源澄清、带资源的短目标、空目标和不支持请求。指标至少包括决策准确率、意图准确率、缺槽集合准确率、拒识准确率与错误样例；没有标注数据或独立评分器前，不报告 Top1/置信区间。

## 非目标与后续门禁

本切片不做指代消解、词汇表、动态 few-shot、语义/向量召回、模型分层、学习型置信度、长期记忆或跨引擎路由。它不能修改现有严格 Task API 的显式引擎选择，也不能让规则绕过权限、预算或资源校验。

模型化意图路由的首个离线/影子门禁见 [模型化意图路由：离线评测与影子门禁](INTENT_MODEL_EVALUATION.md) 与 ADR-0016。它不改变本切片：引入轻量/深度模型、向量检索或用户可见路由前，仍须单独批准数据范围、连接、阈值、影子回放和回滚；见 TD-021。
