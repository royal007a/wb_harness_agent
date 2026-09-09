# HarnessAgent Spec

HarnessAgent 是一个面向 Agent 应用研发与运行治理的独立项目。本仓库目前只建立规格、架构、接口、执行计划和证据规则，不包含业务实现。

项目目标是用统一任务契约连接不同 Agent 引擎，并提供持久状态、权限控制、工具执行、可观测性和评测能力。各引擎通过可选适配器接入，不要求部署在同一进程，也不允许隐式跨引擎跳转。

## 文档入口

- [P2 长期记忆规划](plan.md)
- [产品范围](docs/harness/PRODUCT_SCOPE.md)
- [产品需求](docs/harness/PRD.md)
- [P0 数据分析场景](docs/harness/P0_DATA_ANALYSIS.md)
- [目标架构](docs/harness/ARCHITECTURE.md)
- [现状架构](docs/harness/CURRENT_ARCHITECTURE.md)
- [代码地图](docs/harness/CODE_MAP.md)
- [API 规格](docs/harness/API.md)
- [核心领域契约](docs/harness/CORE_CONTRACTS.md)
- [适配器契约](docs/harness/ADAPTER_CONTRACT.md)
- [工具与沙箱](docs/harness/TOOL_AND_SANDBOX.md)
- [模型与模态路由](docs/harness/MODEL_ROUTING.md)
- [四类 Agent 框架接入路线](docs/harness/FRAMEWORK_INTEGRATION.md)
- [领域映射](docs/harness/DOMAIN_MAP.md)
- [开发约定](docs/harness/CONVENTIONS.md)
- [质量门禁](docs/harness/QUALITY.md)
- [安全与数据](docs/harness/SECURITY_AND_DATA.md)
- [运维规范](docs/harness/OPERATIONS.md)
- [Harness 实施清单](docs/harness/HARNESS_IMPLEMENTATION.md)
- [阅读与改造计划](docs/harness/READING_AND_CHANGE_PLAN.md)
- [技术决策索引](docs/harness/TECH_DECISIONS.md)
- [CodeAct 系列阅读总结](docs/research/SMOLAGENTS_CODEACT_SERIES.md)

## 状态来源

- `harness/tasks.json` 是任务状态的唯一机器真相。
- `harness/state.json` 保存当前阶段与检查点。
- `harness/progress.md` 设计为自动生成的人类摘要；生成器完成前是标记清楚的手工快照，不反向写状态。
- `exec-plans/` 保存可审计的执行计划。
- `harness/evidence/` 保存测试、评测、发布和健康检查证据。

当前 Proposed 的首个真实引擎适配器是 Smolagents CodeAgent，图片理解路由按用户要求指定为 `doubao-seed-2.1-turbo`，两者都必须先通过官方版本核验、能力探针和评审。在规格评审通过前，不引入运行时依赖、不开始实现。
