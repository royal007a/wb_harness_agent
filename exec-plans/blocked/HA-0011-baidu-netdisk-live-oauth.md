# HA-0011 百度网盘真实 OAuth 连通验证

状态：blocked，未执行真实第三方 OAuth 或文件访问。

阻塞：本项目尚未配置用户在百度网盘开放平台创建的应用、精确回调登记、公开 App Key，以及 macOS Keychain 中的 Client Secret。系统不搜索、复制或要求在群聊粘贴凭证。

恢复条件：用户完成官方应用创建，在其后台登记 `http://127.0.0.1:8765/api/local/connectors/baidu-netdisk/callback`，在本机服务环境配置公开 App Key，并通过 Keychain Access 写入服务 `HarnessAgent.BaiduNetdisk`、账户 `oauth-client-secret`。随后用户自行完成浏览器登录和授权；使用独立测试账号和非敏感资料。

后续范围：核验官方授权 URL、callback、token 交换和刷新是否与用户应用当前版本兼容；记录无密的结果和 scope。目录、下载、预览、分享链接导入与文档解析仍不在本任务范围，继续受 TD-020 和独立数据面设计门禁约束。
