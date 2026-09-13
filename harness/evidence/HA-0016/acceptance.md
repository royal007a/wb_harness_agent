# HA-0016 验收记录

状态：passed（2026-09-13）。

## 验收范围

- 收紧 Proposed 的离线 `execution-control@1`，不新增 Product API、数据库迁移、模型/工具调用或 Run 恢复。
- 反例必须被 Schema 拒绝：无 supporting Evidence 的 `supported` Claim、没有 restore 能力的 `restorable` Checkpoint、没有 Try/Confirm/新 Run 绑定的 `confirmed` Replan。

## 必须通过

- 控制夹具、反例契约测试与全量 pytest；
- 任务 Schema、Markdown 本地链接与 diff 检查；
- Evidence 明确标识无模型调用、无 Product Run 恢复、无运行时 Replan API。

## 验收结果

- Schema 现在机械拒绝无 `supporting_evidence_ids` 的 `supported` Claim、带未解决反证的 `supported` Claim、没有 restore 能力的 `restorable` Checkpoint，以及没有 Try/Confirm 摘要与新 Run 引用的 `confirmed` Replan。
- `validate_claim_evidence` 额外验证跨对象的 Evidence 存在性、可靠性和验证状态；JSON Schema 不能独自完成跨记录引用校验的边界被保留为显式 reducer 责任。
- `HARNESS_DOCKER_TESTS=1` 全量回归为 141 passed；`sh harness/verify.sh` 为 130 passed / 11 skipped；仅有既存 Starlette `BlockingPortal` 弃用警告。
- 没有 Product Run、SQLite、模型、工具或网络调用，也没有用户可见 Replan API；ADR-0017 保持 Proposed。
