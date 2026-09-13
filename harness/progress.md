# HarnessAgent 进度摘要

> 本文件应由 `harness/tasks.json` 与 `harness/state.json` 自动生成。当前尚无生成器，因此仅作为初始快照；任务状态仍以 JSON 为准。

- 当前阶段：`local_agent_lab_verified`
- 是否开始实现：是，用户于 2026-09-12 授权本地初版前后端和部署
- 当前任务：无；`HA-0024` 已完成本地 Agent Lab 的 Provider/Model/Agent Profile、Session、POST SSE 与浏览器验证；不增加真实模型路由或读取模型凭证。
- 最近完成：`HA-0024` 已将六份 Provider/Skill/Agent/Chat PDF 的设计结论映射为 ADR-0021 的独立本地数据面：无密配置、SQLite Session/Message/Exchange、幂等与 POST SSE。浏览器、Schema、OpenAPI、链接、全量回归和 launchd 均通过，证据位于 `harness/evidence/HA-0024/`。
- 已记录证据：三份 PDF 阅读（18 页、SHA-256、官方交叉核验）；L0 静态验证；Claude 独立复审 Approved；Git 基线 `4aacf5a3c2eb`
- Backlog：`HA-0002` 核心契约与模拟纵向切片；`HA-0003` Smolagents/远程沙箱探针；`HA-0004` Smolagents P0 适配器；`HA-0005` Doubao 图片理解探针
- 当前阻塞：`HA-0008` 仍等待本项目批准的模型端点、模型 ID、凭证引用和预算；TD-020 未关闭，百度网盘文件数据面与内容解析仍不开放；TD-021 未关闭，意图模型、向量/RAG 和长期记忆尚未进入运行时；TD-022 禁止将 ADR-0019 的固定候选 TCC 表述为自由 Plan 编辑或通用 Agent Replan；TD-024 禁止把 Local Agent Lab 表述为真实 Provider/模型接入或 Agent Loop。
- 当前发布：`0.1.0-local`，http://127.0.0.1:8765
- 最后检查点：HA-0021 已验收。固定 LocalAnalyticsAdapter 在 `resource.inspect` 后生成版本化 Checkpoint；只有带 `ARTIFACT_PUBLICATION_FAILED` Event Evidence 的 failed 源 Run 才在同一失败提交创建唯一 `node_publish`、`evidence/core` 的 open `gap@1`，并可创建白名单恢复 Plan。Try / Confirm / Cancel 仍遵循摘要 CAS：Confirm 以 Plan、Checkpoint、Task、资源、适配器、有效权限和剩余预算摘要创建新 Run；其后仅执行 `checkpoint.verify` 与原有两个发布动作。只有该新 Run 成功，才写 `gap.resolved` 并将源 Gap 改为 resolved；Try、Cancel、绑定漂移与恢复失败均不可解决 Gap。JUnit 为 163 个用例、0 failure/error、11 既有环境跳过（152 passed）；浏览器临时部署 10 项检查通过，含 Gap 创建/解决、不重复 `resource.inspect`。模型、适配器网络和任意代码调用均为零；没有自由 Plan 编辑或通用 Agent Replan。HA-0014 的真实模型路由仍未开启。百度网盘 OAuth 的真实一次 refresh 仅访问官方 token endpoint，且无文件 API 调用/无密 Evidence；分享链接 Skill 仅交接官方客户端。连接入口 `/connectors/baidu-netdisk`。OAuth 数据面关闭，Claude SDK 0.2.152 仅做离线配置验证。

本地切片按 ADR-0009/0010/0011 独立授权完成。真实 VM 与脚本模型驱动的 Smolagents SDK 探针已有证据；完整 P0 冻结、生产沙箱、真实 LLM/Claude SubAgent 与 Doubao 能力验收仍未完成，不将固定函数编排等同于完整 Agent。
