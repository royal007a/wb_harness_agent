# HarnessAgent 进度摘要

> 本文件应由 `harness/tasks.json` 与 `harness/state.json` 自动生成。当前尚无生成器，因此仅作为初始快照；任务状态仍以 JSON 为准。

- 当前阶段：`recovery_loop_guard_completed`
- 是否开始实现：是，用户于 2026-09-12 授权本地初版前后端和部署
- 当前任务：`HA-0039` 已完成独立 Recovery Loop Guard：服务端 Error Contract、失败点/根因假设/回滚 Checkpoint/Replan 起点、Try/Confirm/Cancel、硬停止、软 Reminder，以及回到 HA-0037 Handoff + Gate 的交付约束；不执行模型、工具或实际恢复。
- 当前检查点：全量回归为 225 passed、12 skipped、0 failed（一个上游弃用警告）；定向 Team 契约为 7 passed。两端 Team Runtime 均固定 `agent_runtime=not_connected`、模型/外部工具为 0。它不是 Workspace/Channel/Inbox、真实身份、Daemon、真实 Agent 或 Subagent。
- 最近完成：`HA-0026` 已将投研多 Agent 的主控、财务、行业、风险分工映射为 ADR-0023：每个 Child Run 固化第一方 Skill 摘要、唯一只读工具和二步预算；父级仅汇总复算验证的 Evidence。API、页面、取消/重跑/重启、Schema、并发/越权反例、全量回归和浏览器均通过，证据位于 `harness/evidence/HA-0026/`。
- 已记录证据：五份 Harness 课程 PDF 已全文抽取并按页渲染抽查，哈希和采纳/拒绝边界见 `docs/research/HARNESS_STABILITY_AND_SUBAGENT_READING.md`；HA-0039 Evidence 位于 `harness/evidence/HA-0039/`。
- Backlog：`HA-0002` 核心契约与模拟纵向切片；`HA-0003` Smolagents/远程沙箱探针；`HA-0004` Smolagents P0 适配器；`HA-0005` Doubao 图片理解探针
- 当前阻塞：`HA-0038`（Inbox/work mark/execution lease/freshness）依用户决定暂缓；它仍需要先冻结 Workspace/Channel/Thread 的身份与权限语义。`HA-0027` 仍等待批准的 Claude 模型身份/费用、精确允许域名、搜索/财务 endpoint、Keychain 引用和 Public PDF，之后才可执行 L3。TD-017/018/019/025/026/029/030 禁止将当前实现描述为真实 Claude、多 Agent 并发、真实金融数据、真实 Provider、身份授权、实际恢复或可用于投资判断的系统。
- 当前发布：本机 launchd `http://127.0.0.1:8765` 与远端 systemd/nginx `https://118.196.123.132/harness/` 已同步 HA-0039。两端均完成 SQLite 在线备份、health 与 Recovery Runtime/OpenAPI 检查；远端 staging 预检、`pip check`、nginx 配置检查和服务 active 均通过，公网未认证返回 401。两端 Agent Runtime、模型和外部工具调用仍为零。HA-0039 无密 Evidence 位于 `harness/evidence/HA-0039/`。
- 最新检查点：HA-0026 已验收。三角色父/Child Run、第一方 Skill SHA-256、唯一只读 Tool、二步 Action/Observation/Final 模拟和父级复算汇总均通过；全量回归为 171 passed、11 skipped、0 failed/error，浏览器 9 项检查通过。模型、Provider、网络和外部工具调用均为零；真实 Claude SDK、金融数据与联网检索仍未启用。
- 历史检查点（HA-0021）：固定 LocalAnalyticsAdapter 在 `resource.inspect` 后生成版本化 Checkpoint；只有带 `ARTIFACT_PUBLICATION_FAILED` Event Evidence 的 failed 源 Run 才在同一失败提交创建唯一 `node_publish`、`evidence/core` 的 open `gap@1`，并可创建白名单恢复 Plan。Try / Confirm / Cancel 仍遵循摘要 CAS：Confirm 以 Plan、Checkpoint、Task、资源、适配器、有效权限和剩余预算摘要创建新 Run；其后仅执行 `checkpoint.verify` 与原有两个发布动作。只有该新 Run 成功，才写 `gap.resolved` 并将源 Gap 改为 resolved；Try、Cancel、绑定漂移与恢复失败均不可解决 Gap。模型、适配器网络和任意代码调用均为零；没有自由 Plan 编辑或通用 Agent Replan。HA-0014 的真实模型路由仍未开启。百度网盘 OAuth 的真实一次 refresh 仅访问官方 token endpoint，且无文件 API 调用/无密 Evidence；分享链接 Skill 仅交接官方客户端。连接入口 `/connectors/baidu-netdisk`。OAuth 数据面关闭，Claude SDK 0.2.152 仅做离线配置验证。

本地切片按 ADR-0009/0010/0011 独立授权完成。真实 VM 与脚本模型驱动的 Smolagents SDK 探针已有证据；完整 P0 冻结、生产沙箱、真实 LLM/Claude SubAgent 与 Doubao 能力验收仍未完成，不将固定函数编排等同于完整 Agent。
