# 现状架构

## 结论

当前仓库已具备 **本地工作台 v0.1**：原生 JavaScript/CSS 前端、FastAPI API、SQLite 持久状态、固定 CSV 分析适配器、无模型 Intent Contract 预检和 launchd 部署。另有 Colima VM 沙箱、真实 Smolagents SDK + 脚本模型探针、离线 Skill CLI、本地固定函数 Child Run 编排、Claude SDK 离线配置契约探针、合成去标识的模型化意图离线/影子评测门禁，以及已验证 OAuth 连通但数据面关闭的百度网盘连接器；尚无真实模型、原生 Claude 子 Agent 执行、网盘数据访问或长期记忆。

```mermaid
flowchart LR
  UI[本地浏览器] --> API[FastAPI / 同源边界]
  API --> SVC[Service / 权限 / 幂等 / Run]
  SVC --> DB[(SQLite / 资源 / 状态 / 事件 / 产物)]
  SVC --> W[单 Worker / LocalAnalyticsAdapter]
  W --> V[数值回算 / 产物验证]
  V --> DB
  DB --> UI
```

服务地址、运行限制、重启语义与当前接口见 [LOCAL_WORKBENCH.md](LOCAL_WORKBENCH.md)。此前规格阶段的治理结构保留如下。

独立开发验证链路：`harness/probe.py → ScriptedProbeModel → Smolagents CodeAgent → SandboxExecutor → Colima VM`，与生产 Run 路由隔离。脚本模型不会被注册为用户可选引擎。探针范围见 [ENGINE_PROBES.md](ENGINE_PROBES.md)，项目 Skill 示例见 [SKILL_EXECUTION.md](SKILL_EXECUTION.md)。

因此，本文只描述可验证的现状。目标能力见 [ARCHITECTURE.md](ARCHITECTURE.md)，不得把目标图当作已实现系统。

本地研究演示由 `Service → Research → bounded executor pool → ResearchDemoExecutor` 执行，同一 SQLite 保存父子 Run/事件/产物。最多 9 个子任务、全局 3 个并发，原始输入在 Task 中固定，子执行器只接收各自资源，主任务汇总结构化引用。上下文分发隔离不是线程级安全沙箱。恢复和部分失败语义见 [MULTI_AGENT.md](MULTI_AGENT.md)。

本地分析表单在创建 Task 前调用 `Service → IntentRouter`。该 Router 用 `rules@1` 只识别 CSV 分析，返回 `ready`、`clarification_required` 或 `rejected`；不持久化自然语言输入、没有模型调用，也不会自动创建 Task 或换引擎。规则与固定评测见 [INTENT_ROUTING.md](INTENT_ROUTING.md)。

模型化意图路由仅有离线/影子评测准备：`fixture → candidate-output validator → evaluator → policy gate`。夹具是手写合成去标识数据；没有模型客户端、生产文本或 API 路由接入。候选即使通过也只可申请下一阶段影子回放，详见 [INTENT_MODEL_EVALUATION.md](INTENT_MODEL_EVALUATION.md)。

百度网盘连接器由 `Service → BaiduNetdiskConnector → openapi.baidu.com / macOS Keychain` 组成。SQLite 仅保存 state 摘要、期限和无密状态；Client Secret、access token 和 refresh token 留在 Keychain。当前仅 OAuth 连接，不启用目录、下载或分享链接。见 [BAIDU_NETDISK_CONNECTOR.md](BAIDU_NETDISK_CONNECTOR.md)。

## 当前文件结构

```text
harnessagent/
├── AGENTS.md
├── README.md
├── plan.md                      # P2 长期记忆规划（Proposed）
├── backend/                     # 本地 API / 控制面 / SQLite / 固定工具
├── frontend/                    # 工作台 / API 说明
├── tests/                       # 契约 / 故障 / 浏览器测试
├── deploy/                      # 本机 launchd 配置
├── docs/
│   ├── harness/                 # 当前有效规格
│   ├── research/                # PDF 阅读与官方资料核验
│   └── decisions/               # 架构决策记录
├── specs/
│   └── v1/                      # Draft 核心 Schema、OpenAPI 与运行时策略
├── exec-plans/
│   ├── active/
│   ├── completed/
│   └── blocked/
├── harness/
│   ├── task.schema.json
│   ├── permissions.schema.json
│   ├── tasks.json
│   ├── state.json
│   ├── progress.md
│   ├── permissions.yaml
│   └── evidence/
└── tech-debt-tracker.md
```

## 当前数据流

```mermaid
flowchart LR
    U[需求与评审] --> S[docs/harness]
    S --> T[harness/tasks.json]
    T --> P[exec-plans]
    P --> E[harness/evidence]
    E --> T
    T --> R[harness/progress.md]
    D[重要决策] --> A[docs/decisions]
    A --> S
```

这是一条研发治理信息流，不是线上请求处理链路。

## 已具备

- 项目范围、PRD、P0 数据分析流程、目标架构、API 草案和领域地图；
- 规范、质量、安全、运维与技术决策框架；
- Product Task/Run Draft Schema、机器工作项 Schema、任务队列、阶段状态和权限策略 Draft；
- 三份 CodeAct/Smolagents PDF 的阅读记录与部分官方文档核验；
- active/completed/blocked 计划目录与 Evidence 约定。

## 尚未具备（完整目标能力）

- 生产服务、完整控制台、多进程 Worker 或 SDK；
- 引擎、模型、工具、MCP 或知识系统接入；
- 生产数据库迁移、独立队列与对象存储；
- 身份系统、租户隔离和密钥系统；
- 完整 CI/CD、生产监控、告警和发布环境；本地测试已建立。

## 真实 Agent 实现门槛（本地切片以 ADR-0009 为准）

1. 产品范围、P0 场景和非目标获批。
2. 统一 Task/Run、事件、适配器和工具契约通过契约测试并定稿。
3. 首个纵向切片计划明确，默认使用模拟适配器。
4. 身份、隔离、权限、数据保留和威胁模型有决策记录。
5. Smolagents、远程沙箱和 `doubao-seed-2.1-turbo` 图片输入能力探针完成。
