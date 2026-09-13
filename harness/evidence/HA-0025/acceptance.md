# HA-0025 验收记录

时间：2026-09-13（Asia/Shanghai）。范围见 ADR-0022 与执行计划。

## 已验收

- `agent-runtime@1` 固化独立 Provider、Model、Agent、Session、Message、Exchange 与 SSE 合同；所有对象使用 `runtime_*` SQLite 表，且不读写 Product Task/Run/Plan/Evidence/Checkpoint。
- Provider 只可保存无密 `keychain://harnessagent/<name>` 引用；秘密样式输入、未知字段、外部 HTTP、禁用依赖、幂等冲突均由 API 拒绝。
- OpenAI-compatible Chat Completions SSE 协议 Adapter 已实现；Anthropic/Ollama 明确标记未实现，不降级或伪造回答。
- 默认环境没有 `HARNESS_AGENT_RUNTIME=enabled`，因此每次消息创建可审计 Exchange 并返回 `MODEL_RUNTIME_DISABLED`，不创建 synthetic assistant message；默认模型、Provider、网络、工具调用均为 0。
- 激活的测试 Adapter 验证了 system prompt 与严格最近 `2 × max_context_turns` 历史窗口，以及仅成功流可以持久化 assistant message。
- 本机浏览器验证 Profile 链、零网络 readiness、POST SSE error、无演示回答、历史和窄屏布局；远程 HTTPS 反向代理使用同一浏览器用例，均无页面错误。
- Ubuntu 24.04 远程镜像采用独立 `/opt/harnessagent`、`harnessagent.service`（仅 `127.0.0.1:8765`）和 nginx `/harness/` 路径。nginx Basic Auth 拒绝未认证请求；认证路径、静态资源和 POST SSE 全部验证。现有 nginx 业务未改写，部署前配置备份已保留在服务器 root 私有目录。

## 命令与结果

```text
sh harness/verify.sh
158 passed, 11 skipped, 1 warning

.venv/bin/python tests/browser_agent_runtime.py
default_runtime_gate, provider_readiness_zero_network, profile_chain, session,
post_sse_error, no_synthetic_answer, persistent_exchange, mobile_layout；errors=[]

HARNESS_TEST_URL=https://<host>/harness + HTTP Basic Auth
.venv/bin/python tests/browser_agent_runtime.py
同一组浏览器检查通过；errors=[]

.venv/bin/python harness/agent_runtime_evidence.py
Runtime 契约、静态 OpenAPI、任务 Registry、118 条本地 Markdown 链接和两组浏览器 Evidence 通过。
```

## 部署边界

远程镜像的 Provider Runtime 保持关闭，未复制本机 SQLite、Keychain 或任何模型凭证。服务的 HTTPS 证书由主机既有 nginx 管理；若浏览器提示自签名证书，需要先确认主机指纹。访问 Basic Auth 凭证只在部署交接消息中提供，绝不写入仓库或 Evidence。

## 有意未覆盖

真实模型/Provider 调用、Keychain secret 解析、Provider 网络健康检查、模型成本/预算、Tools/MCP/Skills、ReAct、子 Agent、RAG、长期记忆、多租户身份、真实数据分级和数据外发授权都尚未实施，受 TD-025 与 L3 门禁约束。
