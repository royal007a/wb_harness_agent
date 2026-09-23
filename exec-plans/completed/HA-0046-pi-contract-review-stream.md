# HA-0046：Pi 合同审查 ChatPanel 事件流适配

## 目标

将课程 21 的 ChatPanel 事件语义接入现有 Public PDF 离线流水线，不开启模型、网络或文件执行。

## 已实现

- `POST /api/local/pi-contract-pipeline/review-stream` 要求 `Accept: text/event-stream`。
- 按 `preview` → `finding` → `done` 顺序发送结构化事件。
- 事件只包含 chunk 摘要、Evidence 引用和状态/计数，不发送合同正文。

## 非目标

- 不实现真实 Provider、模型回复、浏览器鉴权或自动 Gate。

## 验收

- 流式接口回归验证三类事件、顺序、无原文和零外部调用字段。
- 全量 Harness 验证通过；本机与公网双部署健康检查通过。
