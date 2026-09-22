# ADR-0023：投研多 Agent 的受控模拟垂直切片

- Status: Accepted（本地模拟切片）
- Date: 2026-09-19

## Context

课程中的行业、财报、风险三个 Claude Agent SDK SubAgent 需要模型、受审查的 Skills、联网检索、金融数据与隔离执行环境。现有 `engine_local_research_demo` 只有固定函数扇出，无法表达一个 Agent 的 Skill / Tool / Observation 合同；ADR-0022 的聊天运行时则明确不含工具或 Child Run。

用户授权先实现 HA-0026 的契约和模拟垂直切片，但未授权真实 Provider、数据外发、WebSearch/WebFetch 或金融数据源。

## Decision

新增独立 `engine_research_multi_agent_simulation`，而不改变历史 `/research` 演示：

1. 一个父 Run 为每个公司创建三个 Child Run：`financial`、`industry`、`risk`。每个 Child Run 固化一个 `research.<role>@1` Agent 定义、一个第一方本地 instruction-only Skill 摘要和仅 `resource.inspect` 的权限。
2. 子 Agent 运行固定的两回合模拟循环：`agent.turn.started → skill.loaded → resource.inspect → tool.result → agent.finalized`。这不是模型推理，也不伪造 Claude SDK 调用；所有模型、Provider、网络和外部工具调用均为零。
3. Tool Runtime 只允许该 Child Run 已分配的 synthetic 资源，校验调用 Schema、权限、资源摘要、64 KiB 输出上限和 Child 预算。未知工具、越权资源、权限漂移、Skill 摘要漂移和预算耗尽均拒绝并留下事件。
4. 父 Run 在有界并发（全局最多 3）后只汇总已验证的 Child 产物。报告同时写入逐 Agent / Skill / Tool evidence、覆盖状态与明确的“风险未评估”边界；缺失风险资料绝不变成低风险判断。
5. Task 中固化 Agent / Skill / Tool 注册表快照和摘要；Run Event 关联所有步骤。重跑创建新树，不复用或覆写旧证据；取消、超时和重启复用 Child Run 终态语义。

## Consequences

- 得到可验证的三角色编排、Skill 加载和受控 Tool Runtime 垂直链，但它仍是本地确定性模拟，不是原生 Claude Agent SDK SubAgent，也不证明任意 Skill 安全。
- 真正接入前需单独关闭 TD-017（SDK 运行探针）、TD-018（隔离）、TD-019（金融数据）及 TD-025（Provider / 数据外发），并以新 ADR 批准每一类外部工具和数据源。
