# ADR-0022：本地 Provider / Model / Agent / Chat Runtime 的受控激活

- Status: Accepted
- Date: 2026-09-13

## Context

六篇 Provider、Skill、Agent 与流式聊天 PDF 要求把 Provider、Model、Agent、Session/Message、上下文窗口和 `POST + SSE` 作为明确的系统边界。ADR-0021 的 Local Agent Lab 仅验证了无密配置和确定性演示回复，不能宣称为模型运行时。

HarnessAgent 已有 Product Task/Run 控制面；不能为了聊天功能混用其状态、权限、证据或恢复链路。

## Decision

新增独立的 **Local Agent Runtime**：

1. Provider、Model、Agent、Session、Message、Exchange 使用独立 SQLite 表和 `agent-runtime@1` 契约；不读取或写入 Product Task/Run 表。
2. Provider 只保存无密 `credential_ref`，格式为 `keychain://harnessagent/<name>`；秘密值不进入 SQLite、日志、SSE、页面或测试证据。
3. `ProviderAdapter` 是协议翻译层：它不拥有业务策略、工具授权、记忆或任务状态。首个实际协议实现为 OpenAI Chat Completions SSE；Anthropic/Ollama 只可配置，未实现时明确拒绝，绝不静默降级或模拟回答。
4. 外部模型调用双门禁：环境变量 `HARNESS_AGENT_RUNTIME=enabled` **且** Provider Profile 有凭证引用。默认关闭；当前默认 Credential Resolver 不能读取凭证，因此即使声明引用也返回可解释的 `MODEL_CREDENTIAL_UNAVAILABLE`。
5. 每次对话先持久化用户消息和 Exchange，再只取 Agent `max_context_turns` 所允许的最近历史。运行时失败写结构化 Exchange 状态，不伪造 assistant 消息。
6. 浏览器使用 `fetch` 的 POST SSE 与 `AbortController`；断开只中止显示，不改写已经持久化的 Exchange。无工具/MCP/Skill 执行，工具绑定数始终为零。

## Consequences

- 本地用户获得可维护、可验证的配置与会话系统，并能清楚看到“配置完成”与“真实模型可运行”是两件事。
- 真实模型需要后续单独提供 Provider 端点、模型 ID、Keychain credential reference、数据分类与预算授权，并通过健康、超时、取消、红队和 L3 验证；本 ADR 本身不授权发送数据到外部。
- Local Agent Lab 保留为 ADR-0021 的历史演示，不升级或重命名为真实运行时。
