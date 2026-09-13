# HA-0017 验收记录

状态：passed（2026-09-13）。

## 范围与通过条件

- 评估器只读取 Adapter descriptor，不执行 probe、适配器、工具、模型、网络、SQLite 或 Product Run。
- 四项能力 `state.checkpoint`、`state.restore`、`control.cancel`、`output.structured` 缺任一即为 `ineligible`。
- 当前 `LocalAnalyticsAdapter.describe()` 必须稳定得到 `ineligible`，缺项为 checkpoint 与 restore；即使合成 descriptor 完整，也只能到 `eligible_for_runtime_probe`，`runtime_enabled=false`。
- 全量 pytest、默认 verify、任务 Schema、链接和 diff 检查通过。

## 验收结果

- 当前 `LocalAnalyticsAdapter.describe()` 的真实结果被确定性判为 `ineligible`，缺少 `state.checkpoint` 且 `state.restore=false`；这与 `restore_run` 的明确拒绝一致。
- 合成完整 descriptor 最多得到 `eligible_for_runtime_probe`，仍固定 `runtime_enabled=false`；准入评估不会探测、注册或启动 adapter。
- 完整回归为 142 passed；`sh harness/verify.sh` 为 131 passed / 11 skipped；仅有既存 Starlette `BlockingPortal` 弃用警告。
- manifest 明确无模型调用、无 adapter probe、无 Product Run 恢复和无用户 Replan API。
