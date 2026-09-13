# HA-0025：本地 Provider / Agent / Chat Runtime

## Objective

依据六篇 PDF，在不改写 Product Task/Run 控制面的前提下，交付一个独立、可部署、可验证的 Provider → Model → Agent → Session/Message → POST SSE 系统。

## In scope

1. `agent-runtime@1` 契约和 ADR-0022。
2. 无密 Provider/Model/Agent 创建链、Provider Adapter 工厂与明确健康/激活状态。
3. 会话、历史窗口、Exchange、结构化失败、POST SSE 和浏览器取消显示。
4. OpenAI Chat Completions SSE 适配器的受控实现与无网络单元测试；默认环境不调用网络，也无法解析凭证。
5. 文档、L2/L3 测试、浏览器验证、launchd 重启和 Evidence。

## Non-goals

- 使用、读取或存储真实凭证；调用任何外部模型；自动同步模型列表或健康探测网络。
- Tools、MCP、Skills、ReAct、子 Agent、RAG、长期记忆，或把聊天状态写入 Product Task/Run。
- 将 Agent Lab 的确定性演示改写成真实模型能力。

## Acceptance

- Schema 和 API 拒绝秘密、未知字段、错误依赖、未激活/未实现 Provider；运行时从不返回伪造 assistant 内容。
- 上下文严格按 Agent 上限裁剪，Exchange 可幂等回放；失败和中断可解释，且 Product Task/Run 数量不变。
- 默认部署的模型/Provider/网络/工具调用为零；完整测试、浏览器和 launchd 健康检查有 Evidence。
