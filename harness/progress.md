# HarnessAgent 进度摘要

> 本文件应由 `harness/tasks.json` 与 `harness/state.json` 自动生成。当前尚无生成器，因此仅作为初始快照；任务状态仍以 JSON 为准。

- 当前阶段：`semantic_retrieval_admission_gate_completed`
- 是否开始实现：是，用户于 2026-09-12 授权本地初版前后端和部署
- 当前任务：`HA-0035` 已完成 M2-B semantic/vector/RRF 的 Admission Gate：其当前状态为 `not_admitted`、runtime disabled、模型/外部调用均为 0，并把语料、外发、删除/重建、离线相关性与成本/延迟基线固化为启用前的机器 Evidence 条件。`HA-0027` 的原生 Claude 投研实现/离线验证仍等待真实 L3 连通授权。
- 当前检查点：ADR-0031 已通过 checked-in fail-closed、伪 not-admitted、缺 Evidence 的 admitted、完整假设 admitted、Runtime 和重启反例；完整 opt-in 回归为 229 passed、0 failed（一个上游弃用警告）。M2-A/M3-A/M3-B/temporal safety 四套合成评测均通过，模型/外部调用均为零。Gate 不是 embedding/vector、RRF/rerank、真实语料/外发或语义检索实现。
- 最近完成：`HA-0026` 已将投研多 Agent 的主控、财务、行业、风险分工映射为 ADR-0023：每个 Child Run 固化第一方 Skill 摘要、唯一只读工具和二步预算；父级仅汇总复算验证的 Evidence。API、页面、取消/重跑/重启、Schema、并发/越权反例、全量回归和浏览器均通过，证据位于 `harness/evidence/HA-0026/`。
- 已记录证据：三份 PDF 阅读（18 页、SHA-256、官方交叉核验）；L0 静态验证；Claude 独立复审 Approved；Git 基线 `4aacf5a3c2eb`
- Backlog：`HA-0002` 核心契约与模拟纵向切片；`HA-0003` Smolagents/远程沙箱探针；`HA-0004` Smolagents P0 适配器；`HA-0005` Doubao 图片理解探针
- 当前阻塞：`HA-0027` 等待部署者提供批准的 Claude 模型身份/费用、精确允许域名、搜索与财务资料 endpoint、必要的 Keychain 引用及 Public PDF，之后才可执行一次受控 L3。TD-017/018/019/025/026 禁止将当前实现描述为已跑通原生 Claude、多 Agent 并发、真实金融数据、真实 Provider 或可用于投资判断的系统；TD-020 未关闭，百度网盘文件数据面与内容解析仍不开放；TD-021 的模型意图路由仍未入运行时；TD-022 禁止将 ADR-0019 的固定候选 TCC 表述为自由 Plan 编辑或通用 Agent Replan；TD-027/028 分别限制外部 Skill 供应链/生产接入和 Memory M1 的身份、语义/图检索、Reflect 等缺口。
- 当前发布：本机 launchd `http://127.0.0.1:8765` 与远端 systemd/nginx `https://118.196.123.132/harness/` 已同步 HA-0035，均运行 `memory-plane-m3b@1` 并报告 semantic Gate 为 `not_admitted`/`runtime_enabled=false`/zero calls。两端先作 SQLite 在线备份；远端先 staging 预检，再以目标端 `.venv`/`.local`/Evidence 排除的方式发布，`pip check`、服务 active、nginx 配置检查、loopback Runtime 均通过；公网保留既有自签 TLS 与 HTTP Basic Auth，未认证访问返回 401。两端模型、外部资料、外部 Skill 执行和 memory 自动抽取均保持关闭。HA-0035 无密部署 Evidence 位于 `harness/evidence/HA-0035/`。
- 最新检查点：HA-0026 已验收。三角色父/Child Run、第一方 Skill SHA-256、唯一只读 Tool、二步 Action/Observation/Final 模拟和父级复算汇总均通过；全量回归为 171 passed、11 skipped、0 failed/error，浏览器 9 项检查通过。模型、Provider、网络和外部工具调用均为零；真实 Claude SDK、金融数据与联网检索仍未启用。
- 历史检查点（HA-0021）：固定 LocalAnalyticsAdapter 在 `resource.inspect` 后生成版本化 Checkpoint；只有带 `ARTIFACT_PUBLICATION_FAILED` Event Evidence 的 failed 源 Run 才在同一失败提交创建唯一 `node_publish`、`evidence/core` 的 open `gap@1`，并可创建白名单恢复 Plan。Try / Confirm / Cancel 仍遵循摘要 CAS：Confirm 以 Plan、Checkpoint、Task、资源、适配器、有效权限和剩余预算摘要创建新 Run；其后仅执行 `checkpoint.verify` 与原有两个发布动作。只有该新 Run 成功，才写 `gap.resolved` 并将源 Gap 改为 resolved；Try、Cancel、绑定漂移与恢复失败均不可解决 Gap。模型、适配器网络和任意代码调用均为零；没有自由 Plan 编辑或通用 Agent Replan。HA-0014 的真实模型路由仍未开启。百度网盘 OAuth 的真实一次 refresh 仅访问官方 token endpoint，且无文件 API 调用/无密 Evidence；分享链接 Skill 仅交接官方客户端。连接入口 `/connectors/baidu-netdisk`。OAuth 数据面关闭，Claude SDK 0.2.152 仅做离线配置验证。

本地切片按 ADR-0009/0010/0011 独立授权完成。真实 VM 与脚本模型驱动的 Smolagents SDK 探针已有证据；完整 P0 冻结、生产沙箱、真实 LLM/Claude SubAgent 与 Doubao 能力验收仍未完成，不将固定函数编排等同于完整 Agent。
