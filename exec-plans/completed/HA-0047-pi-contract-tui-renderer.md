# HA-0047：Pi 合同审查 TUI 事件渲染边界

## 目标

把课程 22 的事件驱动 TUI 语义落成可运行、可验证的终端渲染器，同时保持 HarnessAgent 默认零模型零网络。

## 已实现

- `harness/pi_contract_tui.py`：渲染 preview/finding/done 元数据事件，限制终端宽度，不打印合同正文。
- CLI 接收 JSONL，未知事件显示 fail-closed 提示。

## 非目标

- 不引入 `pi-tui`、不启动 TypeScript Pi runtime、不执行工具。

## 验收

- 单元与 CLI 回归通过；全量 Harness 验证通过。
