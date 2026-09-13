# 代码地图

## 当前地图

当前本地实现采用 ADR-0009 的精简布局，后续目录提案尚未迁移：

- `backend/app.py`：HTTP 传输、同源边界、资源/任务/事件/产物接口；
- `backend/service.py`：契约校验、权限、幂等、Run 状态、固定工具 Worker；
- `backend/store.py`：SQLite 事务、事件序列、对象读写；
- `backend/analysis.py`：受界限约束的 CSV 统计、报告、SVG、manifest；不执行外部代码；
- `adapters/contracts.py`、`local.py`：固定分析器生命周期与受校验事件/结果边界；
- `adapters/smolagents_probe.py`：仅测试的真实 SDK 与脚本模型桥接；
- `backend/sandbox.py`、`sandbox/`：Colima VM 容器执行协议与镜像，不在宿主执行模型代码；
- `backend/readiness.py`、`harness/probe.py`：只读就绪状态与显式探针命令；
- `backend/research.py`：固定深度 Child Run 扇出、全树预算、并发、失败/取消/重跑/恢复；
- `backend/baidu_netdisk.py`：固定官方 OAuth 端点、一次性 state、Keychain 令牌边界；不处理文件数据面或分享链接；
- `harness/configure_baidu_netdisk.py`：用户本机 TTY 配置助手；无回显 Client Secret 只进 Keychain，公开 App Key 仅注入当前登录会话；
- `adapters/research_demo.py`：自建 synthetic 资料与固定专项函数，非真实研报；
- `adapters/claude_config.py`：实际 SDK AgentDefinition 离线配置验证，无 query/CLI 启动；
- `frontend/research.*`：多专项演示页面；`tests/test_research.py` 和 `browser_research.py` 验证；
- `frontend/baidu-netdisk.*`：本地 OAuth 状态与授权入口；`tests/test_baidu_netdisk.py` 验证；
- `skills/csv-group-analysis/`：项目内 Skill 与确定性 CLI，无自动全局安装；
- `frontend/`：原生浏览器工作台与本地 API 说明；
- `tests/`：后端契约/故障测试与真实浏览器验收；
- `deploy/local.macos.plist`：本机 launchd 服务；
- `harness/init.sh`、`start.sh`、`verify.sh`：初始化、启动、验证。

其余有效文件及读取顺序如下：

| 路径 | 作用 | 状态 |
|---|---|---|
| `AGENTS.md` | 短小项目地图与硬规则 | 当前有效 |
| `docs/harness/` | 产品与工程规格 | 当前有效 |
| `docs/research/` | 来源阅读、官方核验与设计输入 | 研究证据 |
| `docs/decisions/` | 重要决策及后果 | 当前有效 |
| `specs/v1/` | Product Task/Run、OpenAPI 与运行时策略 | Draft，未冻结 |
| `harness/task.schema.json` | 原子任务 Schema | 当前有效 |
| `harness/permissions.schema.json` | 研发授权策略 Schema | Draft |
| `harness/tasks.json` | 机器任务真相 | 当前有效 |
| `harness/state.json` | 当前阶段与检查点 | 当前有效 |
| `harness/progress.md` | 人类可读状态摘要 | 派生文件 |
| `harness/permissions.yaml` | 研发过程风险和授权策略 | 当前有效，不属于产品运行时 |
| `exec-plans/` | active/completed/blocked 计划 | 当前有效 |
| `harness/evidence/` | 结构化验证证据 | 当前有效 |
| `tech-debt-tracker.md` | 技术债和触发条件 | 当前有效 |

## 目标代码布局提案

以下路径只是未来边界建议，需通过执行计划和 ADR 批准后才能创建：

```text
apps/
├── api/                         # 外部 REST/SSE 接口
└── console/                     # 管理、调试与评测界面
packages/
├── contracts/                   # 任务、事件、工具、适配器协议
├── control-plane/               # 项目、路由、状态机、审批
├── context/                     # 上下文装配与引用
├── policy/                      # 权限、预算、数据策略
├── tool-runtime/                # 工具校验与隔离执行
├── skills/                      # 技能包格式与加载器
├── observability/               # trace、指标、审计
└── evals/                       # 数据集、评分器、回归
adapters/
├── mock/
├── smolagents/
├── claude-agent-sdk/
├── deepagents/
└── pi/
workers/
├── agent/                       # Agent Loop 与适配器 Worker
└── sandbox/                     # 一次性远程代码执行协调器
deploy/                          # 环境和发布定义
tests/                           # 契约、集成、端到端、故障注入
```

## 依赖方向

```text
apps → control-plane → contracts
workers → adapters → contracts
tool-runtime → policy → contracts
observability / evals → contracts
```

- `contracts` 不依赖任何具体引擎 SDK。
- `control-plane` 不导入适配器实现。
- 适配器不得直接写控制面数据库，只能通过内部契约报告事件和检查点。
- 应用层不得绕过权限层直接调用工具运行时。

## 定位变更的方法

- API 字段：先查 `API.md` 和 `packages/contracts/`。
- 状态问题：查 Task Service、事件序列、Outbox 和租约。
- 引擎差异：查对应 `adapters/`，不要污染公共协议。
- 框架场景与准入顺序：先查 `FRAMEWORK_INTEGRATION.md`，再查对应 Adapter ADR 和探针 Evidence。
- 工具副作用：查 `policy/`、`tool-runtime/` 和审批记录。
- 结果质量：查 `evals/`、Evidence 和引用链。
