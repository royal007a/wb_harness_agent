# 领域映射

下表是目标边界，不代表已有实现。`阶段` 用于防止 24 个领域同时进入 P0；`模块` 和 `页面` 均为建议归属。

| # | 业务域 | 阶段 | API 路由 | 模块 | 默认适配边界 | 页面 | 关键测试 |
|---:|---|---|---|---|---|---|---|
| 1 | 身份与会话 | P1 | `/identity` | identity | 身份提供商 | 登录/会话 | 鉴权、过期 |
| 2 | 工作空间 | P1 | `/workspaces` | workspace | 无 | 工作空间设置 | 隔离、成员权限 |
| 3 | 项目 | P0-min | `/projects` | projects | 无 | 后续 | CRUD、并发 |
| 4 | Agent 规格 | P0-min | `/agent-specs` | agent-specs | 引擎能力映射 | 后续 | 版本、校验 |
| 5 | 模型与模态路由 | P0-min | `/model-routes` | models | Provider Adapter | 后续 | 能力探针、限流 |
| 6 | 引擎注册 | P0 | `/engines` | engines | Engine Adapter | 后续 | 能力协商 |
| 7 | 引擎路由 | P0-explicit | `/routes` | router | Engine Adapter | 后续 | 确定性、拒绝回退 |
| 8 | Task/Run | P0 | `/tasks`, `/runs` | tasks | Engine Adapter | 任务详情 | 状态机、幂等 |
| 9 | 工作流 | P2 | `/workflows` | workflows | Step Adapter | 流程画布 | DAG、补偿 |
| 10 | 对话 | P1 | `/conversations` | conversations | Message Mapper | 对话调试 | 顺序、截断 |
| 11 | 上下文 | P0-min | `/contexts` | context | Context Mapper | 后续 | 预算、引用 |
| 12 | 技能 | P1 | `/skills` | skills | Skill Loader | 技能目录 | 版本、签名 |
| 13 | 工具 | P0 | `/tools` | tools | Tool Adapter | 后续 | Schema、超时 |
| 14 | MCP 连接 | P1 | `/mcp-servers` | mcp | MCP Client | MCP 设置 | 协议、权限 |
| 15 | 资源 | P0 | `/resources` | resources | Resource Adapter | 资源管理 | CSV、只读挂载；扫描件为 P0.1 |
| 16 | 产物 | P0 | `/artifacts` | artifacts | Artifact Mapper | 产物预览 | 完整性、权限 |
| 17 | 知识 | P2 | `/knowledge` | knowledge | Index Adapter | 知识空间 | 检索、删除 |
| 18 | 批准 | P1 | `/approvals` | approvals | 无 | 待审批 | 绑定、过期 |
| 19 | 策略与权限 | P0 | `/policies` | policy | Policy Engine | 后续 | 默认拒绝、沙箱限制 |
| 20 | 预算与配额 | P0-min | `/budgets` | budgets | Usage Mapper | 后续 | 原子扣减 |
| 21 | 事件与流 | P0 | `/events` | events | Event Mapper | 实时事件 | 顺序、去重、续传 |
| 22 | 可观测性 | P0-min | `/traces` | observability | Telemetry Exporter | Trace 视图 | 关联、脱敏 |
| 23 | 评测 | P0 | `/evaluations` | evals | Evaluator Adapter | 评测面板 | 回算、复现、回归 |
| 24 | 审计与运维 | P0-min | `/audit-logs` | operations | Log Exporter | 后续 | 防篡改、恢复 |

`P0-min` 表示只实现纵向链路所需字段和内部接口，不交付完整管理能力；`P0-explicit` 表示只支持显式选择，不做自动路由。

## 横向不变量

- 所有资源受工作空间和项目边界约束。
- 所有变更操作记录主体、请求、时间、版本和结果。
- 所有外部连接使用密钥引用，不返回明文凭证。
- 所有适配器必须通过契约测试，不能覆盖平台状态机。
- 所有高风险能力由策略层集中决定，默认拒绝未知动作。
