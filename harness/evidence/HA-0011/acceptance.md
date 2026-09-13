# HA-0011 验收：百度网盘真实 OAuth 连通

日期：2026-09-13
状态：通过

## 核验结论

- 用户在本机完成官方授权后，连接器的脱敏状态为 `connected`、`has_token=true`、`data_access_enabled=false`。
- 在用户明确许可下，执行了一次只访问固定官方 OAuth token 端点的 refresh 验证；结果见 `live-refresh.json`。该验证不调用目录、下载、预览或分享链接 API。
- OAuth HTTP 客户端禁用环境 HTTP(S)/SOCKS 代理、不跟随重定向，超时为 10 秒；避免 Client Secret 和 refresh token 经由环境代理。
- Keychain、SQLite 与 Evidence 中均不保存或输出 Client Secret、access token、refresh token、授权 code 或原始响应。

## 证据

- `configuration-helper-precheck.md`：本机无回显配置助手的安全预检。
- `configuration-tests.xml`：配置助手回归。
- `live-refresh.json`：脱敏真实 refresh 结果，标记 `file_api_calls=0`。
- `all-tests.xml` 与 `manifest.json`：完整回归与可复核摘要。

## 不因此开放的能力

列目录、文件下载、预览、分享链接导入和内容解析仍未开放，继续受 `TD-020` 及独立数据面设计/验收约束。
