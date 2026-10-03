# HA-0051 子路径前端与重新部署

## 根因与修复

`/harness/` 被 nginx 去前缀后送至 8765，但页面使用根 `/static`、`/api`，
请求落入同机其他应用，HTML 200 伪装为资源加载成功。修复统一页面、API、
POST SSE、下载、图表和导航的前缀；不劫持其他应用的根路径。

附带修复：HTTP 环境 UUIDv4 幂等键 fallback；390px 导航换行。
保留 CSP、Basic 认证和所有默认拒绝的模型/联网门禁。

## 已运行

- `bash harness/verify.sh`：295 passed / 12 skipped；全部确定性评测和门禁检查通过。
- 根路径 browser_smoke：分析、意图、产物、下载、重跑、导航、窄屏，零 JS 错误。
- loopback `/harness/` 代理 browser_smoke：同上，所有同源请求不逃出挂载路径。
- loopback `/harness/` Agent Lab browser：配置、会话、POST SSE、停止、持久记录与窄屏通过。
- 路径测试覆盖全部 7 个页面、CSS/JS MIME、非法前缀、UUID fallback。

截图及机器结果位于 local/、local-prefixed/。截图二进制按仓库规则不提交。

## 发布验收

尚在发布中，远端结果将在 release 后补充。账号和口令不修改、不收集。
本地代理测试不等于公网 Basic 登录测试；网盘只检查页面资源/导航，不读凭据，
不验证 OAuth。默认关闭的真实模型、外部检索能力不会因本次 UI 发布被宣称启用。
