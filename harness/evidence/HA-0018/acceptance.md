# HA-0018 验收记录

状态：passed（2026-09-13）。

## 范围与通过条件

- Probe 在 `harness/` 中使用内存状态，不能在 `Service.adapters` 或 API/OpenAPI 注册。
- 完成 `Plan → checkpoint → Try → Confirm → restore` 后，恢复状态必须从 `node_publish` 继续，且保留已完成的 `node_inspect`。
- 篡改 checkpoint、state、adapter、resource、effective permissions、remaining limits 的任一摘要，restore 必须拒绝。
- 所有报告必须证明零模型/工具/网络调用，以及零 Product Run 创建/恢复。

## 验收结果

- Probe 实际完成 `Plan → checkpoint → Try → Confirm → restore`，恢复点为 `node_publish`，已完成节点为 `node_inspect`；TCC 状态严格为 `proposed → trying → awaiting_confirmation → confirmed`。
- checkpoint、state、adapter、resource、effective permissions、remaining limits 六项摘要逐项篡改均被 restore 拒绝。
- 完整回归为 143 passed；`sh harness/verify.sh` 为 132 passed / 11 skipped；仅有既存 Starlette `BlockingPortal` 弃用警告。
- probe 输出为零模型/工具/网络调用、零 Product Run 创建/恢复和 `runtime_route_registered=false`；它没有注册进 `Service.adapters`。
