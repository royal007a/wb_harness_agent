# HA-0019：本地固定分析器 Checkpoint / Restore 产品纵向切片

状态：completed（2026-09-13）。用户已在当前话题明确批准受限 Product adapter 的 checkpoint/restore 纵向切片；source Run、预算和状态的自洽篡改拒绝已通过最终验收，Evidence 位于 `harness/evidence/HA-0019/`。

## 目标

让 `engine_mock_analytics` 在一个严格固定的提交边界保存持久 Checkpoint；当原 Run 在该边界之后以 `failed` 或 `expired` 终结时，用户可显式创建一个新的、受绑定的恢复 Run。旧 Run 不变，新 Run 只能复用同一 Task、资源版本、有效权限、剩余预算与适配器版本。

## 固定边界与范围

1. 适配器仅在 `resource.inspect` 已完成、固定统计指标已得到并通过输入完整性检查后创建一个 Checkpoint。
2. Checkpoint 持久化于本地 SQLite，保存版本化状态和摘要绑定；不保存原始 CSV、目标正文、Prompt、密钥、网络数据或模型上下文。
3. `POST /api/local/runs/{run_id}:restore` 只接受空 JSON 对象与幂等键；源 Run 必须同一固定分析器的 `failed` 或 `expired` 终态，且存在最新 verified Checkpoint。
4. 恢复前机械重验 Task ID、资源 ID/SHA-256、适配器 descriptor、有效权限、剩余预算和 Checkpoint 内容摘要；任何不匹配拒绝，且不得创建新 Run。
5. 恢复 Run 为新 Run：`based_on_run_id` 指向旧 Run，另记录 `restored_from_checkpoint_id`；它只发布基于已验证统计状态的受控产物。
6. 工作台仅在可恢复的失败/超时 Run 上显示“从检查点恢复”；按钮不等于通用 Replan。

## 明确非目标

- 通用 Plan/Replan API、候选计划编辑、TCC UI 或跨引擎恢复；
- 模型、网络、任意代码、工具扩权、资源/目标/权限变更；
- 从 `cancelled` 或 `succeeded` Run 恢复；
- 原 Run 状态或事件重写、原产物覆盖，或跨 Task 恢复；
- 把单用户本地原型描述为生产级灾备。

## 实施顺序

1. 更新 Core/adapter/API machine contract，新增本地 Checkpoint Schema 和稳定错误码。
2. 实现 SQLite append-only Checkpoint 存储、适配器的固定状态序列化/恢复及 Service 的兼容重验。
3. 接入受限本地恢复端点、OpenAPI 和工作台可见性；保留普通 rerun 语义。
4. 做 L3 契约、故障注入、适配器漂移、资源/权限/预算篡改、取消拒绝、重启和浏览器验收。
5. 生成 Evidence，更新现状架构、安全、质量、运维和技术债；完成后移入 `completed/`。

## 验收条件

- `LocalAnalyticsAdapter` 显式声明且通过固定边界的 checkpoint/restore 能力测试；当前 admission 不再把它列为缺能力。
- 一个 checkpoint 后的注入失败可创建新恢复 Run；新 Run 只发布一次产物，其关键指标与 Checkpoint 状态相符，旧 Run 保持终态。
- Checkpoint、资源、适配器、权限、预算、Task 或源 Run 状态任一不兼容都以稳定错误码拒绝，且没有新 Run/产物副作用；即使篡改者重算 Checkpoint 自身摘要，也不得扩大预算、替换源 Run 或以错误统计状态创建恢复 Run。
- 取消的 Run 永远不能恢复；重复同一恢复请求只返回同一新 Run；服务重启后的失败 Run 可按同一规则判断。
- 后端 L3 回归、静态检查和浏览器验收通过；Evidence 明确模型、网络、任意代码调用均为零。
