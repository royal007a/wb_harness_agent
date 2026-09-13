# HA-0010 百度网盘官方 OAuth 连接底座验收

日期：2026-09-13。范围为本机官方 OAuth 授权码连接底座；不代表已读取、下载或解析任何百度网盘文件。

## 结果

- 本机页面 `http://127.0.0.1:8765/connectors/baidu-netdisk` 与状态 API 已部署。未配置时按钮禁用，连接器返回 `not_configured`、`has_token=false`、`data_access_enabled=false`。
- 98 项完整测试通过（含 Docker/Colima 探针），无失败、错误或跳过；OAuth 专项 10 项覆盖配置缺失、URL/state、回调拒绝/过期/重放、错误 token、刷新、断开和 Keychain 写入故障。
- OAuth 页面 5 项、原工作台 12 项浏览器检查通过，桌面与 390px 布局无浏览器错误。结构化结果见 `manifest.json`、`security-results.json`、`browser.json`、`workbench/browser.json` 和 `all-tests.xml`。
- 本机服务重载后 `/api/v1/health` 与脱敏连接状态均正常；启动使用 `--no-access-log`，避免 callback 的授权 code 进入访问日志。

## 安全边界

- 只生成固定 `https://openapi.baidu.com` 的官方授权/令牌流程，scope 为 `basic,netdisk`，回调地址固定为本机地址。
- 一次性 state 十分钟失效；SQLite 只留摘要、时间与无密状态，绝不保存完整 state、code、Client Secret、access token 或 refresh token。
- Client Secret 和 token 仅经 macOS Keychain 服务 `HarnessAgent.BaiduNetdisk` 使用；断开只删除本机 token，不修改百度账户或文件。
- 无爬虫、Cookie 复用、模拟登录、验证码处理、分享链接下载、列目录、文件下载、预览或数据导入接口。

## 可重复验证

```sh
HARNESS_DOCKER_TESTS=1 .venv/bin/python -m pytest -q --junitxml=harness/evidence/HA-0010/all-tests.xml
.venv/bin/python tests/browser_baidu_netdisk.py
HARNESS_BROWSER_EVIDENCE=harness/evidence/HA-0010/workbench .venv/bin/python tests/browser_smoke.py
.venv/bin/python harness/baidu_netdisk_evidence.py
.venv/bin/python -m pip check
node --check frontend/baidu-netdisk.js
```

## 未完成的外部前提与回滚

真实 OAuth 尚未执行：须由用户创建官方应用、登记精确回调并在本机 Keychain 安全配置 Client Secret 后，用户自行登录授权；该验证转入 HA-0011。不要在群聊发送 Secret、token 或 callback code。

回滚：回退本次提交、重启 `local.harnessagent.workbench`；保留 `.local/backups/pre-ha0010-20260913.db`，不删除用户数据或 Keychain 项。真实授权若已发生，需先在连接页面执行“断开授权”，再按需从 Keychain Access 删除对应条目。
