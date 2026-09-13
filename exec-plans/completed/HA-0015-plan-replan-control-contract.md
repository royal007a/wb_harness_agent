# HA-0015 Plan / Replan 执行控制合同

状态：completed（2026-09-13）。仅覆盖离线控制面合同；不开放运行时 Replan。

## 目标与非目标

目标：将 G4C、TAO、六出口、Evidence/Gap/Checkpoint 可信状态传播与 TCC 写为版本化 Schema、纯 reducer、评测和文档，使未来动态适配器有明确安全准入边界。

非目标：修改现有 CSV/研究 Run 语义；调用模型、工具或外部服务；新增用户 API；从当前本地适配器恢复；修改用户目标、输入资源或权限。

## 现状证据

- `LocalAnalyticsAdapter.describe()` 声明 `state.restore=false`；`restore_run` 明确拒绝。
- 研究演示只支持固定函数 child run、取消和整树 rerun。
- Core Contracts 已有 Checkpoint/restore 目标契约，但当前 Local Workbench 未实现模型 checkpoint。

## 变更步骤

1. 定义 execution-control@1 的 PlanRevision、Evidence、Claim、Gap、CheckpointProjection、ReplanAttempt、G4C/TCC 输入合同。
2. 实现不访问运行时的确定性 reducer：候选 Action 硬过滤、六出口、可靠性传播、Try 校验和 TCC 转移。
3. 用去标识夹具验证正常路径、缺口澄清、Retry、Replan、Interrupt、失效传播、当前 restore 拒绝、权限/预算扩大和确认/取消。
4. 同步 ADR、架构/API/质量/安全/现状文档、技术债和治理状态。
5. 执行 L2 级别回归、Schema/链接/敏感信息检查，形成 Evidence；验收后移入 completed。

## 风险与授权点

状态和未来 API 属于高风险契约变更。此任务只写离线合同，不创建或恢复 Product Run；真实模型、Checkpoint state_ref、外部副作用、权限扩大和 API 发布都需要单独批准。

## 验证矩阵

- Schema：拒绝未知字段、非法 ID、未绑定计划摘要和非法 TCC 枚举。
- Reducer：未注册 Action、未满足硬前提、越权或超预算均不可 `continue`。
- 可信状态：invalid/dirty 对所有下游依赖传播，循环依赖拒绝。
- Try：无 restore 能力、摘要不匹配、权限/预算扩大明确拒绝；兼容受限候选才可通过。
- 回归：完整 pytest、`harness/verify.sh`、前端语法、`git diff --check`。

## 回滚与 Evidence

代码与文档均为新增的离线合同；若需回退，删除本任务文件和新模块，不迁移数据库、不影响现有 API/Run。Evidence 已写入 `harness/evidence/HA-0015/`。
