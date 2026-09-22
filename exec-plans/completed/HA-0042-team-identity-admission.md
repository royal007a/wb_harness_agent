# HA-0042：冻结 Team 真实身份认证准入决策包

状态：completed（2026-09-22，负责人选择 C：仅设计）。

风险：high（身份、正文访问和公网信任边界；本任务未实现认证）。

## 目标

在实现 Channel/Thread/DM 正文前，把当前 nginx Basic Auth、FastAPI 本机入口和 Team protocol `actor_id` 的信任断层转为负责人可选择、可验收、不会偷换概念的身份接入决策。

## 范围

1. 记录当前信任边界与 `actor_id` 不能作为登录 principal 的事实；
2. 比较 OIDC + PKCE、受控 nginx principal header 映射和仅设计三条路径；
3. 固化选项所需输入、subject mapping、撤销、审计、CSRF/header spoof 与 Agent delegation 边界；
4. 负责人已选择 C：保持 metadata-only，不创建 Public identity probe，不改变运行态。

## 非目标

- 不接入 OIDC、改 nginx、创建账户、读取/保存秘密、修改登录配置或部署；
- 不持久化消息正文、附件、Thread/DM、检索、真实 Agent、模型、工具或 Provider；
- 不把 Basic Auth 401、protocol identity 或 `actor_id` 写成已实现的真实认证。

## 完成条件与结果

- ADR-0038/准入文档已定位现有断层、三条路线、不可越过的安全约束和最小输入；
- 负责人于 2026-09-22 明确选择“保持当前 metadata-only 控制面，不实施认证”；
- 已复核本机和远端 Session runtime 继续报告 `protocol_identity_authentication=not_connected`、`agent_runtime=not_connected`、`runtime_telemetry=not_connected`、外部模型/工具调用均为 `0`；
- 本项无代码、nginx、账户或服务配置变更，不触发双环境部署。决策证据见 `harness/evidence/HA-0042/`。

## 后续触发条件

只有负责人将来明确改选 OIDC + PKCE 或受控 nginx principal 映射，并提供对应的非秘密信任边界、责任人和 Public probe 范围，才可创建新的独立实现 Work Item。该 Work Item 仍必须从 Public 合成范围开始，不能借本决策直接开启 Team 内容面或 Agent delegation。
