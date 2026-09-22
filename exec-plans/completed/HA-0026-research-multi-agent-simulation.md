# HA-0026：投研多 Agent 契约与模拟垂直切片

## Objective

在不启用任何模型、Provider、网络、真实金融资料或第三方 Skill 的条件下，交付主控与财务 / 行业 / 风险三 Child Agent 的可审计运行契约、受控 Skill / Tool 模拟、并发汇总和报告证据。

## Delivered

1. ADR-0023、`research-agent-runtime@1` Schema 与三个第一方 instruction-only Skill。
2. 独立 `engine_research_multi_agent_simulation`、`/api/local/research-agents` 和 `/research-agents`；历史 `/research` 固定函数演示未改变。
3. 每个 Child Run 固化 Agent、Skill SHA-256、`resource.inspect`、二步预算；执行 Action → Observation → Final 事件链，父级仅汇总独立复算通过的 Child artifact。
4. 覆盖并发、Skill/权限/资源漂移拒绝、部分风险资料、取消、重跑、重启、API/OpenAPI、桌面和窄屏浏览器验收。
5. Evidence 记录全量回归与浏览器结果；模型、Provider、网络、外部工具调用全部为零。

## Non-goals retained

原生 Claude Agent SDK SubAgent、真实模型/Provider、WebSearch/WebFetch、财报 PDF/行情源、第三方 Skill、真实研报和投资建议未实现；见 TD-017/018/019/025/026。
