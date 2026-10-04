# HA-0074：固化业务模型接入决策

## 目标与范围

记录用户确认的业务用途、精确模型/端点、每 Run 2000 万 Token 预算和套餐用途声明；核对现有接入差距，避免后续重复澄清或误开聊天/离线门禁。

只修改 ADR-0074、本计划、任务登记与本任务 evidence；不实现或部署 Runtime，不接触凭证，不新增外部请求。

## 验收与停止条件

- 决策记录区分用户确认、实现约束和未验证事实。
- 保留原有准入档案及运行时源码不变，Token 不冒充金额。
- 任务登记通过现有 JSON Schema，`git diff --check` 通过。
- 文档核对完成即停止；业务模型接入需后续实现及独立验收，不以此任务 completed 冒充 Runtime completed。

## 交付

- `docs/decisions/ADR-0074-business-model-selection.md`
- `harness/evidence/HA-0074/acceptance.md`
