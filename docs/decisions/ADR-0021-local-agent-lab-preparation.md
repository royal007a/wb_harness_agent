# ADR-0021：本地 Agent Lab 的无模型准备切片

状态：Accepted（2026-09-13，用户授权本轮实现）。这是配置和流式交互准备，不扩大任何真实模型或 Agent runtime 的授权。

## 背景

用户提供的 Provider、Skill、Agent 和对话引擎六篇阅读材料说明：配置模板、会话数据和流式交互需在真实模型接入前建立清晰边界。HarnessAgent 当前 P0 只允许本地确定性 CSV 分析；真实模型、外部 Provider 网络调用、Claude SDK 执行、动态工具调用和长期记忆均未通过准入。

## 决策

1. 新增一个仅面向可信本机用户的 Agent Lab，采用独立 SQLite 文档表保存 Provider Profile、Model Profile、Agent Profile、Chat Session、Chat Message 和幂等 Chat Exchange。它们不写入 Product `Task`、`Run`、Event、Evidence、Gap 或 Checkpoint 表。
2. Provider Profile 只保存名称、类型、基础地址和启用状态；Model Profile 保存展示名、调用标识、上下文窗口和启用状态。二者都不含 API Key、OAuth token、`credential_ref`、健康探测结果或远端模型列表。
3. Agent Profile 固定为身份信息、System Prompt、一个 Model Profile 引用、temperature、max output tokens、max context turns 和启用状态。工具绑定在本切片固定为空；配置不表示系统可调用任何工具或模型。
4. Chat Session/Message 有状态、可持久化、按 Session 隔离。`POST` 消息接口用 SSE 输出 `delta` 与 `done`；内容由确定性的 Local Demo Responder 生成，明确标记 `model_calls=0`、`provider_calls=0`。前端使用 `fetch` 读取 POST 流，支持错误和用户取消显示。
5. 创建/更新不接收未知字段，写入行为要求幂等键并保存请求摘要绑定；UI 使用 `textContent`，不把消息或 Prompt 渲染为 HTML。
6. 新增规格、API、浏览器验收、故障/幂等/隔离测试和本地部署验证。服务健康与引擎状态继续如实显示为“真实模型未启用”。

## 非目标

- API Key、密钥引用、模型健康检查、远端模型同步、网络调用或 Provider Adapter 执行；
- ReAct、Function Calling、MCP/Skill 自动加载、多 Agent、RAG、持久记忆或对话摘要；
- 使聊天输入能够创建/修改 Task、Run、Plan、权限、Evidence、Gap 或 Checkpoint；
- 把演示文本当作用户问题的模型答案，或声称 Claude/任意 Provider 已接入。

## 后果

该切片能用真实浏览器链路验证配置建模、会话隔离、状态持久化、POST SSE、取消和安全渲染，但不验证真实模型质量、延迟、费用、凭证治理或外部取消。后续真实接入必须单独处理 TD-016、TD-017、TD-022 与 TD-023，并经 L3 门禁。
