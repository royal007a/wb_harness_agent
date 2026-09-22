# HA-0042：冻结 Team 真实身份认证准入决策包

状态：waiting_approval

风险：high（身份、正文访问和公网信任边界；此任务不实现认证）。

## 目标

在实现 Channel/Thread/DM 正文前，把当前 nginx Basic Auth、FastAPI 本机入口和 Team protocol `actor_id` 的信任断层转为负责人可选择、可验收、不会偷换概念的身份接入决策。

## 范围

1. 记录当前信任边界与 `actor_id` 不能作为登录 principal 的事实；
2. 比较 OIDC + PKCE、受控 nginx principal header 映射和仅设计三条路径；
3. 固化选项所需输入、subject mapping、撤销、审计、CSRF/header spoof 与 Agent delegation 边界；
4. 等待负责人选择后，再创建对应的最小 Public identity probe Work Item。

## 非目标

- 不接入 OIDC、改 nginx、创建账户、读取/保存秘密、修改登录配置或部署；
- 不持久化消息正文、附件、Thread/DM、检索、真实 Agent、模型、工具或 Provider；
- 不把 Basic Auth 401、protocol identity 或 `actor_id` 写成已实现的真实认证。

## 完成条件

- ADR-0038/准入文档能定位现有断层、三条路线、不可越过的安全约束和最小输入；
- 负责人明确选择一条路径并提供该路径的非秘密配置/责任边界，或明确维持仅设计；
- 被选择路径才可拆为独立实现 Work Item；未选择前运行态与双环境部署不变。
