# HA-0018 隔离 Checkpoint / Restore 纵向探针

状态：completed（2026-09-13）。仅在 `harness/` 内运行确定性 probe，不注册 Product adapter 或 API。

## 目标与非目标

目标：实际演练最小闭环 `Plan → checkpoint → Try → Confirm → restore`，验证摘要绑定、TCC 转移和恢复状态不会只停留在静态 Schema。

非目标：接入 `Service.adapters`、创建 SQLite Task/Run、暴露 API、调用模型/工具/网络，或声称 `engine_checkpoint_probe` 是可选运行时引擎。

## 验证

Probe Adapter 仅持有不透明的内存状态；它声明所需能力但 admission 结果仍是 `eligible_for_runtime_probe`、`runtime_enabled=false`。测试必须验证恢复到正确节点、对 resource/adapter/权限/预算/状态摘要的篡改拒绝、以及输出不存在 Product Run/模型/工具/网络调用。
