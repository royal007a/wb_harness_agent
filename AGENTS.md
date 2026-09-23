# HarnessAgent 项目地图与硬规则

## 项目定位

- 本项目是独立、厂商中立的 Agent 工程控制面。
- 统一任务、状态、权限、工具、事件、产物与评测契约。
- Agent 引擎均为可选适配器，不把任一引擎变成核心领域模型。
- Harness 是研发治理结构，不是产品运行时，也不是第五套 Agent 框架。
- 用户于 2026-09-12 授权初版前后端实现；本地纵向切片范围见 ADR-0009。
- P0 首场景是受控 CodeAct 表格数据分析；联网和多 Agent 属于后续扩展。
- 2026-09-12 用户授权 P1 准备切片：本地固定函数 Child Run 编排演示，见 ADR-0011；不是实际 Claude 运行。
- 图片理解显式路由到用户指定的 `doubao-seed-2.1-turbo`，能力探针通过前不得启用。

## 课程参考资料

- Harness Agent 脚手架实战课本地资料目录：`/Users/weberzhao/Downloads/Harness Agent 脚手架实战课`
- 该目录仅作为阅读、对照和设计参考；课程内容不是本项目已实现能力、规范或准入证据。引用其中方案时，必须落回本项目的契约、ADR、测试和 Evidence。

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

## 竞品开源项目持续跟踪

- 按固定周期（默认每周一次）或用户明确要求，拉取已登记竞品的最新公开仓库、Release 或 commit；只读检查，不把竞品代码直接复制进本项目。
- 每次跟踪必须固定来源 URL、仓库/版本或 commit SHA、抓取时间、许可证和变更范围；“最新”不得只依据搜索摘要或二手转述。
- 阅读后分别记录四类结论：`适合吸收`（符合当前产品范围且有验证路径）、`当前欠缺`（本项目目标范围内尚未具备）、`相对落后`（竞品已有可复核能力而本项目同范围能力缺失或质量较弱）、`暂不适用`（超出范围、信任边界、成本或维护能力）。
- 对“欠缺/落后”必须给出对照证据、影响、优先级和非目标边界；不能把竞品宣传、未验证 Demo 或路线图当成已实现能力，也不能因功能数量多就直接判定技术领先。
- 对“适合吸收”必须补充本项目映射（产品范围、架构模块、契约/API、质量/安全/运维影响）、许可证兼容性和最小验证任务；先写研究记录或 ADR，再决定是否进入 `harness/tasks.json`，禁止在阅读阶段自动改代码或扩大权限。
- 竞品审查产物放在 `docs/research/`，重要结论进入 `docs/decisions/`，实现差距进入技术债或原子 Work Item；每条结论都要能回链到来源、版本和本项目证据。
- 拉取、构建或运行竞品代码时，使用隔离目录和最小权限；不导入本项目凭证、生产数据、Keychain、SQLite 或未批准的网络/模型调用。发现恶意脚本、动态依赖或许可证不清时，停止执行并记录阻塞。

## 变更完成定义

- 任务范围内的验收条件全部通过。
- 相关测试、评测、静态检查和安全检查通过。
- API、事件或数据结构变化已同步规格并说明兼容性。
- Evidence 已写入任务目录并在任务中引用。
- 状态、计划和技术债已更新；无未说明的临时绕行。

## 双环境部署硬规则

- 用户已要求：每次需要部署的实现变更，都必须先部署并健康检查本机 `http://127.0.0.1:8765`，再同步部署到公网主机 `118.196.123.132` 的既有 HarnessAgent systemd/nginx 拓扑；除非用户明确声明“仅本地”或“不部署”。
- 发布前固定版本并运行适用验证；远端先从**当前运行的 systemd 服务**解析 `HARNESS_DB`，确认它位于批准的数据根目录后，对该实际 SQLite 文件创建可恢复备份，再同步应用代码/依赖与版本化部署文件。不得假定默认 `.local/harness.db` 就是远端数据文件。重启后验证 loopback health、受认证的 `/harness/` 代理和新增接口。两端的版本、时间、健康结果和未启用的门禁必须写入对应 Work Item Evidence。
- 远端发布必须先在独立 staging 目录做语法/依赖预检；promotion 到 `/opt/harnessagent` 时，`rsync --delete` 必须再次显式排除并保留远端运行时拥有的 `.venv/` 与数据目录，绝不能把 staging 的排除规则误当成 live-target 的保留规则。若运行环境意外丢失，先如实记录影响、从版本化依赖重建并恢复 health，再继续验收。
- 不在仓库、AGENTS、脚本、日志、Prompt 或 Evidence 写入或回显远端密码、HTTP Basic 密码、token 或其他秘密；凭证仅通过当次受控终端交互使用。远端服务不得复用本机 SQLite、Keychain、测试数据或未批准的运行时开关。

## 当前禁区

- 不实现未批准的运行时。
- 不默认集成全部候选引擎。
- 不直接执行任意模型生成代码。
- 不把业务敏感数据发送给未授权模型或工具。
- 不把路线图能力描述为已实现能力。
