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

应用发布版本：`27ffdf6f7aa6592b60c129d9b14985c3476b38d3`（主修复 `2debad0`）。
本地 launchd 重启，health=ok，model_calls_enabled=false。
远端于 2026-10-03 10:57:48Z 开始发布，从 `8ce252f` 更新；实际数据库
`/var/lib/harnessagent/harness.db` 已用 SQLite backup 备份并通过 integrity_check，
备份目录 `/var/backups/harnessagent/ha0051-20261003T105748Z`，数据库备份 0600。
代码及 nginx 配置也在该目录备份。未迁移数据库 schema，保留 .venv 和数据目录。

远端预检发现原有测试依赖可选 SDK 及开发机全局 Claude CLI：

- 首轮旧线上依赖环境全量：7 failed / 280 passed / 19 skipped，尚未停止或修改线上服务。
- 将可选依赖隔离安装到 `/opt/harnessagent-test-env`，未装入线上 .venv。
- 模拟事件测试把 CLI 存在性哨兵显式绑定到当前 Python（永不执行），不再依赖宿主全局 CLI。
- 最终独立测试环境：289 passed / 18 skipped；线上依赖环境的路径和工作台定向测试：60 passed。
- 线上仍没有 Claude SDK/MCP（原有状态），原生模型相关门禁仍关闭。此次不是原生模型能力验收。

远端浏览器使用**同一生产 nginx snippet**，但通过单独的 `127.0.0.1:18767`
临时 nginx 监听器及 SSH 隧道访问，不更改公网认证。workbench 与 Agent Lab
的样式、导航、CSV 示例、下载、重跑、POST SSE、停止与窄屏均通过，零 JS 错误。
机器结果与截图位于 `remote-nginx/`；临时 nginx 进程和 SSH 隧道已关闭。

公网 HTTP `/harness/` 不再强制跳 HTTPS，HTTP/HTTPS 页面和 CSS 未认证均返回 401；
既有其他站点 HTTPS 根路径仍为 200。systemd/nginx active，nginx -t 通过
（保留已有的重复 text/html gzip MIME 警告，与本修复无关）。

账号和口令不修改、不收集。**未验证用户真实 Basic 密码的正向登录**，任务留在
waiting_approval，等待用户刷新确认。SSH 鉴权下的代理测试不冒充公网 Basic 登录。
网盘仅检查页面资源/导航，不验证 OAuth；不把本次 UI 发布描述为真实模型/外部检索准入。
发布脚本保留了既有 Evidence 目录的远端省略项，远端 git 的证据文件 D 状态不是应用代码漂移。
