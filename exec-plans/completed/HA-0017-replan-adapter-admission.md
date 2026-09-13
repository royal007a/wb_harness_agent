# HA-0017 Replan 适配器准入评估

状态：completed（2026-09-13）。只读取 Adapter capability descriptor 并作离线判定。

## 目标与非目标

目标：为未来 checkpoint-enabled adapter 建立确定性 Replan 准入评估，明确当前本地固定分析器为何不能恢复，并防止“能力名称存在”被误报为已开放运行时。

非目标：探测/执行任何适配器、注册引擎、开放 API、修改 Product Run、调用模型/工具/网络或把 `eligible_for_runtime_probe` 等同生产准入。

## 变更步骤与验证

1. 检查 `state.checkpoint`、`state.restore`、`control.cancel`、`output.structured` 四项必要能力，并兼容布尔和 `{supported:true}` 描述。
2. 使用 `LocalAnalyticsAdapter.describe()` 验证其缺失 checkpoint/restore，结论为 `ineligible`。
3. 使用合成完整 descriptor 验证最高结论仍仅为 `eligible_for_runtime_probe`、`runtime_enabled=false`。
4. 同步适配器合同、执行控制说明、Evidence 和 L2 回归。

回滚：纯函数、测试和文档均不进入 API/数据库路径，可独立回退。
