# HA-0011 百度网盘真实 OAuth 连通验证

状态：completed。用户已完成官方 OAuth 回调，并明确允许一次只刷新 token 的官方验证；未执行文件访问。

已验证：本机授权后的脱敏状态为 `connected`、`has_token=true`、`data_access_enabled=false`。一次 refresh 仅调用固定官方 OAuth token 端点，结果位于 `harness/evidence/HA-0011/live-refresh.json`；其记录 `file_api_calls=0`、`token_material_emitted=false`。

安全加强：OAuth HTTP 客户端固定直连官方 HTTPS endpoint，禁用环境 HTTP(S)/SOCKS 代理和重定向，10 秒超时，不自动重试令牌交换。完整 114 项回归和无密证据索引位于 `harness/evidence/HA-0011/`。

后续范围：目录、下载、预览、分享链接导入和文档解析仍不在本任务范围，继续受 TD-020 和独立数据面设计门禁约束。
