# HA-0042 设计决策验收记录

状态：accepted（选择 C：仅设计）。

## 已完成

- 将当前 nginx Basic Auth、FastAPI 本机入口和 caller-supplied `actor_id` 之间的信任断层写入 ADR-0038；`actor_id` 继续只是 protocol identity，不是 HTTP human principal。
- 对比并保留 OIDC + PKCE、受控 nginx principal 映射与仅设计三条路线的准入条件、停止条件和未来 Public probe 前提。
- 负责人于 2026-09-22 选择保持 metadata-only 控制面，不实施认证；该选择已经同步到 ADR、准入文档、任务登记、状态和已完成计划。

## 边界复核

- 本机 `http://127.0.0.1:8765/api/local/team/sessions/runtime` 与远端服务 loopback runtime 在 2026-09-22 复核均报告 protocol identity、Agent Runtime、runtime telemetry 为 `not_connected`，外部模型/工具调用均为 `0`。
- Team Foundation、Session Continuity 与 Workbench 定向回归为 64 passed、0 failed（一个上游 deprecation warning）。
- 本机和远端 loopback health 均为 `ok`；既有公网未认证入口继续返回 `401`。没有应用代码、nginx、账户、登录会话或服务配置变更，因此本项不部署，也不能声称新增了认证、内容面或真实 Team Agent 能力。

## 不代表

HTTP 登录、OIDC/token、Basic principal mapping、真实 human/Agent identity、Team 正文/Thread/DM/附件/检索、Agent delegation、Runtime、Provider、模型、MCP、工具、网络或真实投研均未实现或放行。

## 重新开启的条件

只有负责人显式改选 OIDC + PKCE 或受控 nginx principal 映射，并提供对应的非秘密信任边界、责任人与 Public probe 范围，才能创建新的独立实现 Work Item；该决定本身不授权任何后续实现。
