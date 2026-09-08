# HA-0001 L0 静态验证

- 时间：2026-09-08T15:09:10Z
- 基线提交：`4aacf5a3c2eb`
- 环境：macOS，本地只读验证命令；没有安装项目运行时依赖。

## 结果

| 检查 | 结果 |
|---|---|
| 6 个 JSON 文件语法 | PASS |
| `harness/tasks.json` 对 `task.schema.json` 的字段、类型、枚举、模式与依赖结构 | PASS |
| API.md 中 5 个 JSON 示例语法 | PASS |
| Create Task 请求与响应对核心 Draft Schema | PASS |
| 3 个 YAML 文件解析 | PASS |
| 研发 `permissions.yaml` 与 P0 运行时 Policy Profile 的状态、默认拒绝、effect 与 conditional requires | PASS |
| OpenAPI 3.1 基本结构和 28 个 `$ref` 文件/片段 | PASS |
| 5 个 Harness Work Item ID、依赖存在与 DAG 无环 | PASS |
| 8 个 ADR 文件、索引与状态一致 | PASS |
| 40 个 Markdown 文件、52 个 Markdown 链接 | PASS，本地目标均存在 |
| 6 个 Mermaid fence 与全部代码 fence 成对 | PASS |
| `AGENTS.md` 行数 | PASS，76 行 |
| 参考系统禁用名称 | PASS，0 命中 |
| 运行时代码和包管理文件 | PASS，0 个 |
| 已勾选但无证据的复选框 | PASS，0 个 |

## Reviewer 指出问题的复核

- Git：已初始化，基线提交为 `4aacf5a3c2eb`。
- `remaining_limits` 与 `resource_handle`：均已定义并被适配器 Schema 引用。
- 权限策略：YAML 已使用 `effect`，Schema 已包含 `requires`。
- API 漂移：叙事文档已改为 Run 级取消/重跑，并声明机器契约的权威位置。
- 任务状态：HA-0001 在本轮设计与自审完成后转入 `waiting_approval`。

## 本次自审新增修正

- 避免 P0 每个代码 Step 都要求人工批准：改为 Task 级授权固定远程沙箱 Profile，超出 Profile 仍拒绝或逐项批准。
- P0 基线严格保持 CSV 输入；Doubao 图片理解移动到 P0.1，探针前不启用，非图片 Task 的 `vision` 为 `null`。
- 四类框架由独立 Adapter 复用平台契约，不在单 Run 中隐式嵌套。
- 研发权限与产品运行时权限已拆分；P0 Policy Profile 位于 `specs/v1/policies/`，Run 固化实际权限和预算版本。

## 局限与后续门禁

- 当前环境没有完整 JSON Schema/OpenAPI/Mermaid 专用校验器；本次使用标准解析器和针对当前契约特性的确定性校验脚本，不等同完整规范一致性认证。
- Mermaid 尚未渲染做视觉布局检查。
- Smolagents、远程沙箱与 Doubao 均未进行真实调用；对应 ADR 仍是 Proposed。
- 以上限制不影响继续独立 review，但在实现或正式发布前必须进入自动 `verify` 矩阵。
