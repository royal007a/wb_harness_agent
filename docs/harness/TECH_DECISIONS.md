# 技术决策索引

本页同时列已接受和正在评审的决策。只有 `Accepted` 才是当前制度；`Proposed` 不得被描述为已实现或已冻结。被替代的 ADR 必须在原文和索引中明确标记，不删除历史。

| ADR | 状态 | 决策摘要 |
|---|---|---|
| [ADR-0001](../decisions/ADR-0001-harness-is-structure-template.md) | Accepted | Harness 只作为研发治理结构 |
| [ADR-0002](../decisions/ADR-0002-provider-neutral-control-plane.md) | Proposed | 核心采用厂商中立控制面契约 |
| [ADR-0003](../decisions/ADR-0003-optional-engine-adapters.md) | Proposed | 引擎通过可选适配器接入 |
| [ADR-0004](../decisions/ADR-0004-durable-async-task-state.md) | Proposed | 使用持久异步任务状态机 |
| [ADR-0005](../decisions/ADR-0005-policy-before-side-effects.md) | Proposed | 所有副作用在执行前通过策略与授权 |
| [ADR-0006](../decisions/ADR-0006-controlled-codeact-p0.md) | Proposed | 以受控 CodeAct 数据分析作为 P0 |
| [ADR-0007](../decisions/ADR-0007-remote-sandbox-for-model-code.md) | Proposed | 模型生成代码使用远程隔离沙箱 |
| [ADR-0008](../decisions/ADR-0008-vision-model-route.md) | Proposed | 图片理解路由使用 Doubao-Seed-2.1-Turbo，探针通过后启用 |
| [ADR-0010](../decisions/ADR-0010-adapter-sandbox-probes.md) | Accepted（开发探针） | Adapter 边界、Colima VM 和明确标记的脚本模型探针；不开放真实路由 |
| [ADR-0011](../decisions/ADR-0011-local-child-run-orchestration.md) | Accepted（本地演示） | 一层 Child Run 扇出、最多 3 并发、固定资料、失败/取消/预算/恢复 |
| [ADR-0012](../decisions/ADR-0012-baidu-netdisk-oauth-connector.md) | Accepted（本地 OAuth 准备） | 官方 OAuth 授权码、Keychain 凭证、无密 SQLite 审计；不爬取分享链接 |
| [ADR-0013](../decisions/ADR-0013-baidu-netdisk-local-configuration-helper.md) | Accepted（本机准备） | TTY 无回显配置助手将 Secret 写入 Keychain；不通过聊天/文件传递凭证 |
| [ADR-0015](../decisions/ADR-0015-local-deterministic-intent-preflight.md) | Accepted（本地受限实现） | 只识别 CSV 分析的无模型 Intent Contract、缺槽澄清与显式提交门禁 |
| [ADR-0016](../decisions/ADR-0016-intent-model-evaluation-gate.md) | Proposed | 模型化意图路由先通过合成去标识离线评测与影子门禁 |

## 待决策

[ADR-0009：本地工作台初版](../decisions/ADR-0009-local-workbench.md) 已在用户实现授权范围内 Accepted：FastAPI、SQLite、原生前端和单进程本地工具。以下服务选型待决项继续适用于生产与真实 Agent 阶段。

- 首个实现语言与服务边界；
- 关系数据库、队列与对象存储；
- 身份与工作空间隔离强度；
- 内部适配器协议（进程内、RPC 或消息）；
- Smolagents 版本、执行器能力与首个真实适配器最终批准；
- `doubao-seed-2.1-turbo` 图片输入端点与能力探针；
- 遥测、评测和远程沙箱具体技术。

这些问题应由验证性证据驱动，不在规格文档中暗设答案。
