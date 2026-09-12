# HarnessAgent 项目地图与硬规则

## 项目定位

- 本项目是独立、厂商中立的 Agent 工程控制面。
- 统一任务、状态、权限、工具、事件、产物与评测契约。
- Agent 引擎均为可选适配器，不把任一引擎变成核心领域模型。
- Harness 是研发治理结构，不是产品运行时，也不是第五套 Agent 框架。
- 用户于 2026-09-12 授权初版前后端实现；本地纵向切片范围见 ADR-0009。
- P0 首场景是受控 CodeAct 表格数据分析；联网和多 Agent 属于后续扩展。
- 图片理解显式路由到用户指定的 `doubao-seed-2.1-turbo`，能力探针通过前不得启用。

## 每次工作前必读

1. `README.md`
2. `docs/harness/PRODUCT_SCOPE.md`
3. `docs/harness/P0_DATA_ANALYSIS.md`
4. `docs/harness/FRAMEWORK_INTEGRATION.md`
5. `docs/harness/CORE_CONTRACTS.md`
6. `docs/harness/CURRENT_ARCHITECTURE.md`
7. 与改动相关的规格文档和 ADR
8. `harness/tasks.json`、`harness/state.json`
9. 对应的 `exec-plans/active/` 计划

## 项目地图

- `backend/`、`frontend/`、`tests/`、`deploy/`：本地工作台实现与验证；使用说明见 `docs/harness/LOCAL_WORKBENCH.md`。
- `plan.md`：P2 长期记忆的设计、治理、阶段路线与验收计划。
- `docs/harness/`：产品、架构、API、规范、质量、安全、运维。
- `docs/research/`：来源阅读与官方资料核验。
- `docs/decisions/`：一项重要技术决策一篇 ADR。
- `specs/v1/`：Product Task/Run 与 API 的机器可读 Draft。
- `exec-plans/active/`：正在执行或评审的原子计划。
- `exec-plans/completed/`：已验收计划和证据链接。
- `exec-plans/blocked/`：阻塞原因和恢复条件。
- `harness/task.schema.json`：任务数据格式。
- `harness/permissions.schema.json`：研发授权策略格式；不得用作产品运行时策略。
- `harness/tasks.json`：唯一机器任务状态。
- `harness/state.json`：当前阶段、运行与检查点。
- `harness/progress.md`：计划由机器状态生成；生成器完成前为标记清楚的快照。
- `harness/permissions.yaml`：研发过程风险和授权策略，不是产品运行时策略。
- `harness/evidence/`：结构化验证证据。
- `tech-debt-tracker.md`：技术债及触发条件。

## 硬规则

1. 先改规格和契约，再改实现。
2. 一次只执行一个原子任务；任务必须有验收条件和范围。
3. `tasks.json` 只保存 `HA-*` 研发 Work Item，是治理状态真相；不得与产品 `task_*` 混用。
4. 外部副作用必须先过权限策略；高风险动作逐项批准。
5. 凭证只允许引用密钥标识，不得写入代码、日志、Prompt 或证据。
6. 工具调用必须校验输入、限定超时、记录审计，并返回结构化结果。
7. 适配器只翻译协议，不承载核心业务规则。
8. 引擎选择必须显式、可解释、可回放；禁止运行中静默换引擎。
9. 完成状态必须附证据；没有证据只能标为进行中或阻塞。
10. 所有长任务必须可取消、可超时、可恢复并受预算约束。
11. 日志、事件和产物必须关联 `workspace_id`、`project_id`、`task_id`、`run_id`；Step 级记录还须关联 `step_id`。
12. 破坏性操作不得扩大目标范围，且优先采用可恢复方案。
13. 发现规格冲突时停止实现，先用 ADR 消解冲突。
14. 不为未验证的未来需求提前抽象。
15. P0 的模型生成代码不得在宿主进程或仅靠本地 AST 限制器执行。
16. 四类框架只通过独立 Adapter 共享平台契约，禁止在同一 Run 内隐式嵌套或静默切换。

## 变更完成定义

- 任务范围内的验收条件全部通过。
- 相关测试、评测、静态检查和安全检查通过。
- API、事件或数据结构变化已同步规格并说明兼容性。
- Evidence 已写入任务目录并在任务中引用。
- 状态、计划和技术债已更新；无未说明的临时绕行。

## 当前禁区

- 不实现未批准的运行时。
- 不默认集成全部候选引擎。
- 不直接执行任意模型生成代码。
- 不把业务敏感数据发送给未授权模型或工具。
- 不把路线图能力描述为已实现能力。
