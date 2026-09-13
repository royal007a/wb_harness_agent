---
name: local-agent-lab-delivery
description: 为 HarnessAgent 的本地 Agent Lab 交付无密配置、会话和 POST SSE 演示；只适用于 ADR-0021 的零模型准备切片。
---

# 本地 Agent Lab 交付 SOP

这是项目内交付 Skill，不会自动安装到个人 Claude/Codex 配置，也不授予网络、模型、工具或凭证权限。

1. 先阅读 `docs/decisions/ADR-0021-local-agent-lab-preparation.md`、`docs/harness/SECURITY_AND_DATA.md`、`docs/harness/QUALITY.md` 和 `specs/v1/local-agent-lab.schema.json`。若需求包含 API key、Token、远端探测、真实模型调用、Tool/MCP、RAG、长期记忆或 Product Run 变更，停止本 Skill，改走独立 ADR 与 L3 准入。
2. 先修改机器契约、API 文档和执行计划，再实现数据/服务/HTTP/UI。Profile 只包含名称、类型、Base URL、启用状态、Model 标识和 Agent 受限参数；不得增加 `auth_config`、`credential_ref` 或不受控 JSON。
3. 实现中保持数据面隔离：Profile/Session/Message/Exchange 不能写入或读取 Task、Run、Event、Evidence、Gap、Checkpoint。消息渲染使用纯文本；POST SSE 只输出版本化 `delta/done/error`，使用 `fetch` 读取；每个写入需要幂等键。
4. 验收必须至少覆盖：未知字段、敏感样式输入、依赖禁用、Session 隔离、消息顺序、幂等重放/冲突、SSE `delta → done`、AbortController、刷新恢复、窄屏布局，以及 `model_calls/provider_calls/network_calls/tool_calls` 全为 0。将环境、命令、结果和截图写入任务 Evidence。

这个 SOP 是方法与验证清单，不是运行时授权。真实 Provider、模型、SDK、Tool 或 Agent Loop 的批准条件仍由控制面、权限与单独 ADR 决定。
