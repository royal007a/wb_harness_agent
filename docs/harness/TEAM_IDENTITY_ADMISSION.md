# Team 身份认证准入与内容面门禁（ADR-0038）

## 现状事实

| 层 | 已有能力 | 不能证明 |
|---|---|---|
| nginx 公网入口 | HTTP Basic Auth、TLS、只代理 loopback upstream | 认证用户名与应用 `actor_id` 的绑定 |
| FastAPI 本机入口 | Host/Origin 本地边界、protocol `actor_id` | 浏览器用户、token、OIDC session 或跨设备 principal |
| Team Foundation | Workspace/Channel/membership/clearance/role 检查 | 请求是谁、是否已登录、是否已撤销 |
| Team Session/Attention | metadata-only 引用、新鲜度与 Handoff | 聊天正文、附件或真实内容权限 |

所以，现有 Basic Auth 的 `401` 只说明入口需要口令；它**不**说明后端已得到可信的 human identity，更不说明 caller-supplied `actor_id` 可以访问 Team 内容。

## 选择后才可开始的切片

| 选择 | 下一 Work Item | 首个可验收范围 | 禁止事项 |
|---|---|---|---|
| OIDC + PKCE | HA-0043 Identity L3 Probe | 单一 Public Workspace、真实登录/登出/过期/撤销、subject mapping、actor mismatch/CSRF/header spoof 反例 | Internal/Restricted 内容、Agent delegation、模型/工具 |
| nginx Basic 映射 | HA-0043 Proxy Principal Probe | 固定受控管理员、可信 header、mapping、unknown/revoked principal 拒绝与反向代理隔离 | 多租户/SSO 声称、敏感正文、Agent delegation |
| **仅设计（当前已选）** | 不创建实现 Work Item | 保持 `actor_id` 为 protocol identity、metadata-only 与零内容存储 | 任何身份/内容代码、nginx 改动或部署变更 |

## 负责人需确认的最小输入

1. 当前选择已完成：保持 metadata-only，不实施认证；
2. 只有未来显式改选 OIDC 时，才需提供 issuer、租户、客户端登记方式、精确 redirect URI、subject/group claim、会话与撤销负责人；
3. 只有未来显式改选 nginx 映射时，才需提供认证用户名到 human identity 的初始 mapping、轮换/撤销负责人、允许的公网入口范围；
4. 任何未来 identity probe 均须先确认只用 Public 合成 Workspace，以及出错时的回滚负责人。

当前选择下，`actor_id` 继续只能用于本机 protocol control plane；Team Channel/Thread 正文与附件不进入 SQLite。没有新的显式路线选择，不创建认证实现或部署任务。
