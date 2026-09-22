# ADR-0024：原生 Claude 投研运行时的受控准入

- Status: Proposed
- Date: 2026-09-19

## Context

ADR-0023 只证明了三角色 Child Run、Skill 摘要、工具边界与父级报告的本地模拟合同。它刻意没有启动 Claude Agent SDK、模型、联网工具或真实财报。课程中的投研场景需要原生 `Agent` SubAgent、三个第一方 Skills、WebSearch/WebFetch、金融资料和可审计汇总；这些能力会把资料发往模型或外部来源，且 SDK MCP 工具运行在应用进程中，不可把 Skill 文字视为安全边界。

本机已固定 `claude-agent-sdk==0.2.152`，其实际 Python 接口含 `query()`、`AgentDefinition`、`create_sdk_mcp_server()` 和 `can_use_tool`。同时安装的 `mcp==2.2.0` 落在 SDK 元数据的允许范围中，但原生查询、SubAgent、工具取消与事件形状均未做真实连通验证。

## Decision

新增独立的 `claude_native_research@1` 准入层，保持与 ADR-0023 模拟引擎分离：

1. Adapter 只把 Claude SDK 消息映射成平台可审计事件，不访问 SQLite 或发布 Run 终态。父 Agent 只可调用原生 `Agent`；财务、行业、风险 Agent 分别得到最小 MCP 工具集、固定 Skill 名称、回合/费用上限和 `dontAsk` 权限模式。
2. 三个 Skills 以仓库内本地插件加载，固定插件整体摘要。Skill 是方法说明，不带 Bash/Read/Edit/浏览器能力，也不被用户或项目级 Claude 设置隐式扩展。
3. MCP 工具只有四类受控只读资料能力：财务 API、新闻搜索、网页抓取和已登记 PDF 文本提取。每个输入有 Schema、域名或资源绑定、超时、字节上限和 `source_evidence` 输出；工具输出只返回受限摘录和来源摘要，原始资料留在受控层。
4. 外部模型或资料访问要求两个独立环境门禁：`HARNESS_CLAUDE_RESEARCH_RUNTIME=enabled` 与 `HARNESS_CLAUDE_RESEARCH_EXTERNAL_DATA=enabled`，并要求模型 ID、正向费用上限、允许域名、数据源端点/凭证引用（如适用）及用户资料分类评审。缺任一条件必须在调用 SDK 或 HTTP 前失败，绝不回退到模拟答案。
5. Native query 事件要保留父 `Agent` tool-use 与 child `parent_tool_use_id` 关系、工具参数摘要、来源证据摘要、SDK 终态/用量与模型文本产物。父报告只能引用拥有来源证据的 Child 报告；资料缺失写为未评估，不产生交易、买卖、ST 或退市结论。

## Consequences

- 仓库获得真实 SDK/Skill/MCP 的可启动实现和默认关闭的可验证门禁，但没有 Provider、允许数据源、真实 PDF 和预算授权时不启动 CLI、不做网络请求，也不能声称“真实多 Agent 已验收”。
- 实际连通后必须新增 Evidence：SDK/CLI/MCP 版本、三个 SubAgent 的真实并发/父子事件、工具取消、成本上限、资料外发与域名拦截、来源引用、PDF 解析失败和完整回滚演练。完成前 TD-017/018/019/025/026 保持开放。
