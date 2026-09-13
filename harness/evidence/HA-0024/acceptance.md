# HA-0024 验收记录

时间：2026-09-13（Asia/Shanghai）。范围见 ADR-0021 与 `exec-plans/completed/HA-0024-local-agent-lab.md`。

## 已验收

- 六份用户提供的 Provider / Skill / Agent / 对话引擎 PDF 已完成阅读、版面抽查与设计映射，摘要见 `docs/research/CLAUDE_CODE_PROVIDER_AGENT_CHAT_SIX_PDFS.md`。
- `local-agent-lab.schema.json` 约束 Provider、Model、Agent、Session、Message、SSE；未知字段、凭证样式文本、URL 用户信息、外部 HTTP、禁用依赖和幂等冲突均被拒绝。
- Agent Lab SQLite Profile/Session/Message/Exchange 与 Product Task/Run/Event/Evidence/Checkpoint/Replan 分表且无互读写路径。
- `POST /api/local/agent-lab/sessions/{id}/messages` 使用 `text/event-stream`，输出 `delta → done`，本地确定性演示器与运行时状态均证明 model/provider/network/tool 调用为 0。
- 浏览器在 `http://127.0.0.1:8765/agent-lab` 验证 Profile 创建、Session、POST SSE、持久历史、停止显示、窄屏布局与无页面错误；截图见同目录 `agent-lab-desktop.png`、`agent-lab-mobile.png`。
- launchd 服务已重启并处于 running；健康端点与 Agent Lab runtime 均返回可用且零调用状态。

## 命令与结果

```text
sh harness/verify.sh
155 passed, 11 skipped, 1 warning

.venv/bin/python tests/browser_agent_lab.py
zero_call_runtime, provider_profile, model_profile, agent_profile, session,
post_sse, persistent_history, abort_ui, mobile_layout；errors=[]

.venv/bin/python harness/agent_lab_evidence.py
Schema、静态 OpenAPI、任务 Registry、110 条本地 Markdown 链接与浏览器 Evidence 通过。
```

## 有意未覆盖

真实 Provider 连接、凭证/凭证引用、模型或 SDK 调用、Tool/MCP、RAG、长期记忆、多租户身份与生产数据治理均未实现。它们仍受 TD-016、TD-017、TD-022、TD-023、TD-024 的独立 ADR 与 L3 门禁约束。
