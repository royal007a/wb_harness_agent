# HA-0011 本机 OAuth 配置助手预检

日期：2026-09-13。此为真实 OAuth 前的本机配置辅助验证，不包含任何百度 App Key、Client Secret、token 或 callback code。

- `harness/configure_baidu_netdisk.py` 仅在交互式 TTY 运行；无回显读取 Client Secret，必须键入 `CONFIGURE` 才发生 Keychain/launchd 写入。
- 自动测试使用替身验证 Keychain service/account、公开 App Key 的 launchctl 命令形状、无效输入拒绝、非 TTY 拒绝、取消无副作用，以及 launchd 失败时异常文本不泄露 Client Secret。
- `HARNESS_DOCKER_TESTS=1 .venv/bin/python -m pytest -q`：107 通过、0 失败、0 错误、0 跳过；JUnit 位于 `configuration-tests.xml`。
- 预检时已部署连接器仍为 `not_configured`、`has_token=false`、`data_access_enabled=false`。没有启动百度网页登录、令牌交换或文件数据面。

下一步仅能由用户在其 Mac 图形登录会话中运行助手并在浏览器自行登录/授权。完成后再执行无密的真实 OAuth 连通验证；任何文件访问继续由 TD-020 单独控制。
