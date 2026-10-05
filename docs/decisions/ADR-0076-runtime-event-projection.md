# ADR-0076：业务 Adapter 观察事件先投影再持久化

- Status: Accepted for implementation
- Date: 2026-10-05

## 决策

吸收方案 A 的第一原子切片：Native Claude 与 Pi 的原始事件只在内存协议通道流转；写入 Product Event 前生成 `runtime-event-metadata@1`。不再将 assistant 文本、消息数组、工具参数/结果、structured_output、SDK errors 或 stderr 正文写入这些观察事件。

投影只输出平台固定 kind、重新计算的完整 payload JSON SHA-256/UTF-8 字节数、严格布尔 is_error（若存在），以及 sdk.result 的 errors 总数、至多前 64 项的摘要/字节数/固定类别 `sdk_error`。未识别 kind 拒绝，未知字段只进入摘要，不复制。JSON 规范化为 ensure_ascii=True、sort_keys=True、紧凑分隔符、allow_nan=False；字节数是该规范化 JSON 的长度，不冒称原始 wire 字节数。

Native 的 tool-use 关联仍在内存中按原 ID 路由；持久 `agent.delegated` 改为 `sdk_tool_use_id_sha256`，原 ID 仅可在已有受控 manifest 产物中出现。文本先供现有 Child 引用校验及聚合使用，再投影；只通过既有 publish() 发布报告。Pi 最终候选仍由 Adapter 内存结果返回并通过原有 Schema/Gate，不从摘要反推正文。此切片不增加主控 structured_output 聚合能力。

Pi EOF 不再读取/传播 stderr，返回固定 PI_SIDECAR_EOF；该子进程 stderr 直接丢弃，避免 PIPE 填满及内容日志。其他侧车协议错误 code 映射为固定 PI_SIDECAR_ERROR，不能把任意 code 当文本外传。

## 兼容及边界

- 新写入的 `agent.sdk.*` payload 和 `pi.*.data.payload` 使用新版本；旧行不改写/不删除，读取仍原样返回，不宣称清除了历史正文。消费者须按 schema_version 分支。
- Product Event 外层、分页、事件类型、Run/Gate/Artifact 状态不变。新投影有单独机器 Schema；通用 Event.data 保持开放，不把本变更冒称全库日志脱敏。
- Hash/长度仍可能泄露相等性与低熵内容猜测，不是匿名化。Task 输入、资源、受控产物、旧事件不在本次清理范围。
- 子进程环境白名单、独立 cwd/退出清理、Native worker、auto memory、真实工具 Provider 桥仍属 A/B 后续任务。模型准入保持关闭；没有真实 CLI/Provider 或系统沙箱验收。
- 发布前全量验证并固定提交；先本机8765再132。若本机 launchd 拓扑不兼容，停止发布，不跳过本机直接推进132。
