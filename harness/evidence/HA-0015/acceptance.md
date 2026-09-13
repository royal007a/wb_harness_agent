# HA-0015 验收记录

状态：passed（2026-09-13）。

## 验收范围

- `execution-control@1` 只定义离线 Plan/Evidence/Gap/Checkpoint/Replan 控制合同；不向本地工作台注册新的 API。
- reducer 只处理调用方传入的结构化状态，不连接 SQLite、不创建/恢复 Product Run、不调用模型、工具或网络。
- 固定夹具仅含合成去标识的 ID、摘要状态、权限和预算枚举；不含用户目标正文、Prompt、资源内容或凭证。

## 必须通过

- 全量 pytest、前端语法与 `git diff --check`；
- Schema 与 13 个固定控制情形全部通过；
- Evidence manifest 明确记录无模型调用、无 Product Run 恢复、无运行时 Replan API。

## 验收结果

- `execution-control@1` Schema 覆盖 PlanRevision、Evidence、Claim、Gap、CheckpointProjection、ReplanAttempt、G4C 输入与评测夹具；所有对象为版本化的摘要/引用结构，拒绝未知字段。
- reducer 和 13 条合成去标识情形覆盖六出口、候选 Action 的注册/前置条件/权限/预算门禁、dirty/invalid 下游传播、无 restore 能力拒绝、权限/预算扩大拒绝、兼容恢复和 TCC；没有模型、工具、网络、SQLite 或 Product Run 调用。
- 全量 L2 回归：`HARNESS_DOCKER_TESTS=1 .venv/bin/python -m pytest -q --junitxml=...` 为 141 passed；`sh harness/verify.sh` 为 130 passed / 11 skipped。两次均仅有既存 Starlette `BlockingPortal` 弃用警告。
- 运行时边界维持不变：本地 CSV 与研究演示不暴露 Replan API，也不支持 restore；ADR-0017 仍为 Proposed。
