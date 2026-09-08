# HA-0001 Claude 独立复审

- Reviewer：`mymacclaude`（open_id `ou_3f1c247d6daaf39dfec1e6975bc964ff`）
- 最终 review 消息：`om_x100b6536c343d530b1b94689d13919b`
- 复审基线：Git commit `3a3248a`
- 结论：**Approved**
- 日期：2026-09-08

## Reviewer 独立验证结论

- 三份 PDF 的 CodeAct、工具/MCP、报告产物和多 Agent 方法已进入主架构，而非仅保留在阅读附录。
- P0/P0.1 边界清晰；P0 为只读 CSV + 远程沙箱 + 受控产物，图片理解在 Doubao 能力探针后才启用。
- Smolagents、Claude Agent SDK、Deep Agents、Pi 的分阶段 Adapter 路线合理，共享 Task/Run/Policy/Tool/Event/Artifact/Evaluation 契约。
- 研发治理权限与产品运行时 Policy Profile 已完全分离。
- Run 固化有效权限和预算，Child Run 只能收窄；Policy Profile 的 4 条 allow/conditional 与 5 条 deny 覆盖 P0 边界。
- 6 个 JSON、3 个 YAML、Harness Work Item 依赖/DAG、本地链接和 Git 工作区均由 reviewer 独立检查通过。
- ADR-0001 为 Accepted，ADR-0002 至 ADR-0008 为 Proposed，没有把未决项描述成已实现事实。

## 非阻塞建议及处理

1. `vision` 的 nullable Schema 改为显式 `oneOf`：已在 `14f06f1` 处理。
2. API 路线图接口增加 P0/P1/P2 阶段列：已在 `14f06f1` 处理。
3. 区分 Task 请求权限与 Run 生效权限：Task 已改为 `requested_permissions`，Run 使用独立 `effective_permissions` 结果结构并保存决策摘要。
4. Policy rule key 限制为至少两段的 `domain.action`：已增加 `propertyNames.pattern`。
5. Doubao 图片输入仍需真实 endpoint 探针：保留在 `HA-0005`，不因 review 通过而视为已完成。

## 冻结状态

技术复审已通过，但 HA-0001 仍保持 `waiting_approval`：只有用户确认 P0 产品范围后，才标为 `completed`、移动计划并进入下一阶段。Review 通过不代替产品范围确认。

