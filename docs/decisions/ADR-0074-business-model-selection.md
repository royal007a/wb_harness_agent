# ADR-0074：业务 Runtime 的豆包模型选择与累计 Token 上限

日期：2026-10-04
状态：模型选择及预算意图已由用户确认；真实 Runtime 接入尚未实现/验收。

## 已确认输入

- 用途：HarnessAgent 的合同审查、投研等业务 Runtime，不是仅配置编程助手。
- 模型：`doubao-seed-2.1-lite`。
- Base URL：`https://ark.cn-beijing.volces.com/api/coding/v3`。
- 协议选择：OpenAI-compatible；实际工具调用、用量、取消与错误兼容性需探针验证。
- 每次业务 Run 累计最多 `20_000_000` Token，不是 20 分钟或单次上下文窗口。
- 用户已确认其套餐允许上述程序化用途；这是用户声明，不是本项目独立核验套餐权益的结果，不再重复要求确认同一用途。
- 确认消息：`om_x100b6310eeed1ca0b3ccf67a596937e`；预算消息：`om_x100b6310dc8b38a8b12d51b5fa59b68`。

凭证不得复制到本记录、代码、Prompt、日志或 Evidence。后续平台传输层只解析 Keychain 引用；本次没有保存或读取凭证。

## 预算实现约束（待实现，不是现有能力）

1. 一个根业务 Run 及其 Child、重试、压缩、护栏二次确认等模型调用共用累计输入/输出账本；不得每个 Child 各领 2000 万。
2. 每次真实请求发出前须原子预留输入上界与输出上限，并受当前剩余额度约束；并发请求不得重复花同一余额。
3. 已发送但没有可靠 usage 的调用不得按零消耗退还；缺用量、取消、断线、异常重试均须保守结算并阻止未知成本下继续调用。
4. 不能仅凭事后 usage 检查就声称硬上限。输入计数上界、Provider 输出上限及隐藏重试都必须经过验证；否则只报告软计量或保持真实执行关闭。
5. 2000 万 Token 不等于金额授权。货币上限尚未确定，不把它换算成 USD/CNY，也不把未知价格当零费用。已有费用准入不得直接删除或用 Token 字段冒充满足。
6. 不自动把 Coding Plan 端点改成 `/api/v3`，不自动换模型或将一次上限扩展成无限次自动运行。

## 当前接入差距与下一步

代码核对基线：`a065e53`。

- `pi-adapter/src/sidecar.mjs` 的 `validateStart` 只接受 Faux/offline-contract-review；真实模型需要独立传输桥接，不能改一项 URL 就生效。
- `backend/pi_contract_review.py` 固定使用离线引擎、零费用和 Faux 模型；现有成功/人工 Gate 不构成真实合同审查证据。
- `backend/provider_adapters.py` 是独立文本聊天传输，拒绝工具调用，不能直接当业务 Agent Loop。
- `docs/harness/CLAUDE_RESEARCH_RUNTIME.md` 和 `backend/claude_research_admission.py` 绑定 Claude CLI/SDK；不能把本 OpenAI-compatible URL 填成 Claude CLI 身份。投研引擎若改用 Pi 或新增适配器，必须另作显式路由决策，不静默替换。
- `pi-admission@1` 还绑定费用、资料源、Public PDF、取消/回滚责任；本确认不是这些条件的替代。合同离线资料场景应单独设计窄准入，不为满足旧格式而编造搜索/财务 endpoint。

建议实施顺序：平台共享预算与传输边界 → 合成输入的受控协议探针 → Public PDF 合同审查 Product Run/Handoff/Gate 纵切 → 投研引擎与来源准入。每一步分别报告离线、真实 Provider、业务验收与部署证据。

## 本次交付边界

仅持久记录已确认决策和实现差距；未改变运行时开关、既有准入档案、认证、数据库、部署或模型配置。没有模型请求、密钥落盘、真实 PDF 外发或新增金融数据授权。不能据此称业务 Runtime 已连接或上线。
