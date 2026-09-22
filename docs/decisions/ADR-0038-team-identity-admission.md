# ADR-0038：Team 内容面前的真实身份认证准入

状态：Proposed（等待负责人选择；未实现）

日期：2026-09-22

## 背景

ADR-0035 至 ADR-0037 已在本机 SQLite 中保存 Workspace、protocol Agent identity、membership、Task、Attention 与 Session Handoff。但请求中的 `actor_id` 仍由调用方提供；它不是登录 principal，也没有 session、撤销、审计或跨设备身份保证。

公网 nginx 已验证 HTTP Basic Auth，却没有将经过认证的用户名以受信方式交给应用。应用因此无法证明 `actor_id` 和浏览器用户有关联。若现在持久化 Channel/Thread/DM 正文、附件或跨人内容检索，会把 protocol metadata 误用为内容访问控制。

## 决定前提

1. **先身份，后内容。** 未把请求解析为不可由调用方伪造的 human principal 前，不实现 Team 消息正文、Thread/DM 正文、附件、内容检索或跨设备协作。
2. **服务器派生 actor。** 完成认证后，human 的 `actor_id` 必须从 server-side subject mapping 派生；HTTP body/query 的 `actor_id` 只能在兼容期被显式拒绝或比对，不能授予权限。
3. **人和 Agent 分离。** Agent protocol identity 不能用浏览器登录伪造；未来 Agent Run 必须有一个经认证 human 创建、可过期/撤销、绑定 Workspace/Channel/Task/能力上限的 delegation grant。它不等价于模型、工具或 Provider 授权。
4. **不把 Basic Auth 当多租户系统。** Basic Auth 可以作为既有受认证反向代理的短期入口，但不足以单独证明 Team 内容面的角色、会话撤销、跨设备 SSO 或 Agent 委派。

## 选项

| 选项 | 适用 | 必要安全边界 | 当前建议 |
|---|---|---|---|
| A：OIDC Authorization Code + PKCE | 多人、跨设备、敏感 Team 内容和后续 Agent 委派 | 固定 issuer/discovery/JWKS、exact redirect URI、state/nonce/PKCE S256、服务端 HttpOnly Secure SameSite session、subject→human identity mapping、登出/撤销/audit | **推荐**，但需负责人提供 IdP 与租户策略 |
| B：nginx Basic Auth → 受信 principal header | 单一受控管理员、快速验证受认证应用路径 | upstream 只能 loopback；nginx 清空外来 principal header 后从 `$remote_user` 重设；app 只接受代理来源；principal→human mapping；禁用公网直接访问；轮换/撤销运维流程 | 仅作为受限过渡，不能直接开放敏感内容或 Agent 委派 |
| C：仅设计，不接认证 | 先审阅方案或尚无 IdP | 保持现有 `actor_id`=protocol identity、metadata-only 边界与零内容存储 | 默认，直到负责人选择 A 或 B |

## OIDC 最小准入字段

- 固定 issuer URL、discovery/JWKS 来源、client ID、精确 redirect URI、允许 audience/azp、subject claim 与 tenant/group claim；不保存 client secret、ID token、access token 或 refresh token 到仓库、日志、Prompt 或 Evidence。
- 受信 subject 到 `human` AgentIdentity 的显式映射；Workspace membership/Channel role/clearance 仍在 Harness 控制面判断，不能由外部 group 静默覆盖。
- session 只保存随机 opaque ID、subject mapping version、认证/过期/撤销时间和最小审计引用；cookie 必须 `HttpOnly`、`Secure`、合适的 `SameSite`，状态变化须有 CSRF 防护。
- authorization-code 流程使用 PKCE `S256`、transaction-bound state 和 OIDC nonce；redirect URI 精确匹配且没有 open redirector。多 issuer 时固定 issuer 或实施 issuer/mix-up 防御。
- 先以一个 Public、无附件、无真实 Agent 的 L3 identity probe 验证登录、登出、过期、撤销、subject/actor mismatch、CSRF、header spoof、Workspace/Channel 隔离和审计，再考虑内容面。

上述协议要求依据 [RFC 9700](https://www.rfc-editor.org/rfc/rfc9700.html) 的 OAuth Security BCP、[RFC 10017](https://www.rfc-editor.org/rfc/rfc10017.html) 的 browser-based application 建议以及 [OWASP OAuth2 Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/OAuth2_Cheat_Sheet.html)。

## Basic 代理过渡的硬约束

- nginx 必须在 `auth_basic` 成功后删除客户端传来的 `X-Harness-Principal`、`X-Harness-Auth-*`，只将 `$remote_user` 写入受信 upstream header；应用不接受相同 header 的公网直连。
- systemd upstream 保持 loopback-only，防火墙/容器网络不得另开端口；本机直接访问只允许明确的 local-admin 开发模式，不能伪装远端登录。
- 应用从受信 header 查找显式 `human` identity mapping，未知、禁用或撤销 principal 一律拒绝；请求携带的 `actor_id` 若存在必须与映射一致，否则拒绝并审计。
- 密码轮换、人员离开、失效和审计由反向代理运维流程承担；缺乏这些证据时，B 不可升级到含敏感正文的 Channel。

## 共同验收与停止条件

- 认证代码/配置与 protocol Team 状态隔离；关闭认证或出现 issuer/header/session 不一致时 fail closed，不回退到 caller-supplied `actor_id`。
- 任何 membership/clearance/identity 状态变化在同一请求的授权点重新读取；审计记录不包含 bearer token、cookie、认证码、密码或消息正文。
- 没有用户选择、IdP/代理信任链、Public probe 数据范围、撤销负责人和回滚方式，不实现身份认证、消息正文或 Agent delegation。

## 非目标

- 此 ADR 不启用 OIDC、修改 nginx、创建账户、读取凭据或部署身份服务；
- 不实现消息正文、Thread/DM、附件、检索、Daemon/Computer、Provider/模型、工具或真实 Agent Runtime；
- 不把 OAuth/Basic 成功当作 Workspace/Channel/Task/Gate 或工具权限通过。
