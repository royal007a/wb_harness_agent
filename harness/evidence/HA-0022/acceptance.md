# HA-0022 验收记录

状态：通过（2026-09-13）。此任务只做图谱能力覆盖审计与治理文档对齐；没有增加模型、网络、任意代码、动态 Action 或 API 行为。

## 预期验证

- 图谱每个模块都清楚标注为已实现、部分实现、离线合同或未授权；
- 技术债反映 HA-0014、ADR-0019 与 ADR-0020 的当前事实，并显式登记通用 TAO runtime 缺口；
- 任务注册表、本地 Markdown 链接和全量回归通过，运行时能力清单不变。

## 实际证据

- `docs/harness/PLAN_REPLAN_CONTROL.md` 已把图谱各模块映射为已实现、部分实现或离线合同，并为通用 TAO runtime 缺口登记 TD-023。
- `python -m pytest --junitxml=harness/evidence/HA-0022/all-tests.xml -q`：163 个用例，0 failure、0 error、11 个既有环境跳过（152 passed）。
- `python harness/plan_execution_coverage_evidence.py`：91 份本地 Markdown 文档链接通过；任务注册表 Schema 通过；运行时清单只有 `engine_mock_analytics` 适配器，`model_calls_enabled=false`，其余真实 Agent 引擎仍是 blocked/planned。
- `node --check frontend/{app,research,baidu-netdisk}.js` 与 `git diff --check` 通过；摘要位于同目录 `manifest.json`。
