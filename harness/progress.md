# HarnessAgent 进度摘要

> 本文件应由 `harness/tasks.json` 与 `harness/state.json` 自动生成。当前尚无生成器，因此仅作为初始快照；任务状态仍以 JSON 为准。

## 当前快照（2026-10-04，独立复核返工）

- HA-0053/0054 已获 mymacclaude Approved，原子范围收口；完整目标没有完成。
- HA-0055 停止作用域/有界终态回查已修复，19 项 UI，独立复审 Approved；
  两条 Low 已登记，等待部署；不是已发布新版本。
- HA-0056 为 Changes Requested：Background 调用方、gui/501=125、user/501
  可查询，本机尚未恢复。慢退出与恢复误判已继续返工，45 项定向、
  全量 390 passed/16 skipped；待新固定提交复审与本机兼容拓扑选择，未部署。
- 132 最后确认版本仍 1840639。模型门禁关闭，Tool bindings=0。

## 历史快照（2026-10-03，HA-0052；非当前状态）

- 应用 `87934de` 已发布到本机和 `http://118.196.123.132/harness/`。
- 外部 Skill 两端明确开启、镜像可用；包与执行仍仅直接 loopback/SSH，公网只
  查看受 Basic 保护的状态。每端 17 项 Skill 测试、真实 API 合成 smoke 通过。
- 本机全量 303 passed / 16 skipped；远端 staging 297 passed / 22 skipped。
- 状态 waiting_approval，备份、镜像供应链与验证边界见 `harness/evidence/HA-0052/`。
- 真实模型/Claude/MCP、Product Run 沙箱接入、多租户、崩溃回收均未因本次开放。

## 历史快照（以下不代表当前部署状态）

- 当前阶段：`native_claude_research_l3_admission_binding`
- 是否开始实现：是，用户于 2026-09-12 授权本地初版前后端和部署
- 当前任务：`HA-0027`。正在为 Native Claude Research 加入版本化、无密的 `claude-research-admission@1`，把 CLI Provider/模型、每 Run USD 费用/turn/时间、精确域名与搜索/财务 JSON connector endpoint、仅 Keychain 引用、单一 Public PDF SHA-256、取消/回滚责任和审批 Evidence 绑定为一个 fail-closed profile。
- 当前检查点：默认 profile 固定为 `not_admitted`，所以模型、CLI、Keychain 与 HTTP 仍为 `0` 调用。完整资料尚未由负责人提供；本次只实现和发布验真边界，不猜测模型、端点、凭据或人名，也不执行真实 L3 Probe。HA-0042 的 metadata-only identity 决策保持不变，不能被该准入档案绕过。
- 最近完成：`HA-0026` 已将投研多 Agent 的主控、财务、行业、风险分工映射为 ADR-0023：每个 Child Run 固化第一方 Skill 摘要、唯一只读工具和二步预算；父级仅汇总复算验证的 Evidence。API、页面、取消/重跑/重启、Schema、并发/越权反例、全量回归和浏览器均通过，证据位于 `harness/evidence/HA-0026/`。
- 已记录证据：五份 Harness 课程 PDF 已全文抽取并按页渲染抽查，哈希和采纳/拒绝边界见 `docs/research/HARNESS_STABILITY_AND_SUBAGENT_READING.md`；HA-0040 Evidence 位于 `harness/evidence/HA-0040/`。
- Backlog：`HA-0002` 核心契约与模拟纵向切片；`HA-0003` Smolagents/远程沙箱探针；`HA-0004` Smolagents P0 适配器；`HA-0005` Doubao 图片理解探针
- 下一步推荐：完成 HA-0027 的测试与双环境发布后，任务回到 `waiting_approval`。届时必须由负责人提供批准的 Claude 模型身份/费用、精确允许域名、搜索/财务 JSON connector endpoint、Keychain 引用名称、单一 Public PDF 和取消/回滚责任，之后才可执行 L3。身份、tenant/session/revocation/audit 与敏感正文保留边界在新的显式选择前保持关闭，不能把 protocol `actor_id`、metadata-only Session 或 Snapshot 用作 HTTP 身份、消息系统、Provider Session 或真实 Agent Runtime。TD-017/018/019/025/026/029/030 禁止将当前实现描述为真实 Claude、多 Agent 并发、真实金融数据、真实 Provider、身份授权、实际恢复或可用于投资判断的系统。
- 当前发布：本机 launchd `http://127.0.0.1:8765` 与远端 systemd/nginx `https://118.196.123.132/harness/` 已同步 HA-0041。HA-0042 是设计决策，未改动应用、nginx 或服务，故没有伪造一次发布；两端 runtime 已只读复核，模型和外部工具调用仍为零。HA-0041 无密 Evidence 位于 `harness/evidence/HA-0041/`，HA-0042 决策 Evidence 位于 `harness/evidence/HA-0042/`。
- 最新检查点：HA-0026 已验收。三角色父/Child Run、第一方 Skill SHA-256、唯一只读 Tool、二步 Action/Observation/Final 模拟和父级复算汇总均通过；全量回归为 171 passed、11 skipped、0 failed/error，浏览器 9 项检查通过。模型、Provider、网络和外部工具调用均为零；真实 Claude SDK、金融数据与联网检索仍未启用。
- 历史检查点（HA-0021）：固定 LocalAnalyticsAdapter 在 `resource.inspect` 后生成版本化 Checkpoint；只有带 `ARTIFACT_PUBLICATION_FAILED` Event Evidence 的 failed 源 Run 才在同一失败提交创建唯一 `node_publish`、`evidence/core` 的 open `gap@1`，并可创建白名单恢复 Plan。Try / Confirm / Cancel 仍遵循摘要 CAS：Confirm 以 Plan、Checkpoint、Task、资源、适配器、有效权限和剩余预算摘要创建新 Run；其后仅执行 `checkpoint.verify` 与原有两个发布动作。只有该新 Run 成功，才写 `gap.resolved` 并将源 Gap 改为 resolved；Try、Cancel、绑定漂移与恢复失败均不可解决 Gap。模型、适配器网络和任意代码调用均为零；没有自由 Plan 编辑或通用 Agent Replan。HA-0014 的真实模型路由仍未开启。百度网盘 OAuth 的真实一次 refresh 仅访问官方 token endpoint，且无文件 API 调用/无密 Evidence；分享链接 Skill 仅交接官方客户端。连接入口 `/connectors/baidu-netdisk`。OAuth 数据面关闭，Claude SDK 0.2.152 仅做离线配置验证。

本地切片按 ADR-0009/0010/0011 独立授权完成。真实 VM 与脚本模型驱动的 Smolagents SDK 探针已有证据；完整 P0 冻结、生产沙箱、真实 LLM/Claude SubAgent 与 Doubao 能力验收仍未完成，不将固定函数编排等同于完整 Agent。
