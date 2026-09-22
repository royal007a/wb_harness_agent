# HA-0027：原生 Claude 投研多 Agent 受控运行时

## Objective

把 ADR-0023 的三角色模拟契约升级为可启动但默认关闭的 Claude Agent SDK 原生 SubAgent / Skill / MCP 资料适配层；实现真实资料工具、事件映射、父子证据和启动前探针，而不在未批准环境中发送模型或金融资料。

## Scope

1. 固定 `claude-agent-sdk==0.2.152` 的真实 Python 接口，建立原生 `Agent`、`AgentDefinition`、本地插件 Skills、进程内 MCP 和 SDK message→platform event 映射。
2. 实现受控的 `web_search`、`web_fetch`、`financial_data` 和登记 PDF 提取工具契约：域名/资源绑定、超时、大小、摘要、来源证据与默认拒绝。
3. 加入本地运行时准入、真实请求模型、父/子 Run 事件和可审计报告的纵向实现；默认关闭外部调用，缺少授权/配置必须无 CLI/网络副作用失败。
4. 覆盖 SDK 构造、MCP 工具 Schema、门禁、事件路由、父级引用、整棵 Run 的持久化取消与真实环境探针指引；真实 Provider/CLI 的取消与费用回报仍由 L3 验收。

## Non-goals

- 不使用聊天中的 API key、Cookie、自动登录或未获批准的本机凭证；不自动发现模型、数据源或域名。
- 不将线程池当作 OS 隔离，不载入第三方 Skill，不输出投资建议，也不伪造真实新闻/财报结论。
- 不把未执行的真实连通配置标为已验收。

## Acceptance

- 默认环境下模型/CLI/Keychain/HTTP 调用均为零，并给出精确 blocker；工具的无配置与越权输入稳定拒绝。
- 已启用的 adapter 通过实际 SDK 类型构造原生父 `Agent` 与三份 Child `AgentDefinition`、本地插件 Skills 和进程内 MCP Tool Server；事件可保留 parent/child tool-use 关联。
- 所有工具输出都可归为有时间、摘要和 URI/资源引用的证据；父级汇总拒绝没有有效证据的 Child 成果；任一 Child 的取消会终止整棵 Run 并保留 L3 transport-cancel 缺口。
- 任务/Run、契约、文档、回归和 Evidence 同步。真实模型/网络/SDK 连通仅在独立、已批准的 Probe 中执行并保留版本、费用、取消和来源证据。

## Checkpoints

1. ADR、Schema、运行时边界和任务状态通过静态检查。
2. Adapter / plugin / source-tool 的离线构造与 failure-path 测试通过。
3. Product Run 集成、事件/报告、取消/预算/域名测试通过。
4. 仅在全部外部授权与配置就绪时执行真实 L3 probe；否则记录 blocker，不能关闭真实验收债务。
