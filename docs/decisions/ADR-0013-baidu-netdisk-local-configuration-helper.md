# ADR-0013：百度网盘 OAuth 本机交互式配置助手

- 状态：Accepted（本机准备）
- 日期：2026-09-13
- 触发：用户选择继续 P2 官方 OAuth 配置，但不得在飞书、源码、环境快照或 Evidence 中传输 Client Secret。

## 决策

提供一个用户自行在本机终端启动的 Python 交互脚本。它从 TTY 读取公开 App Key，使用无回显提示读取 Client Secret，并要求用户键入确认短语后才执行两类动作：经 keyring 写入 macOS Keychain 服务 `HarnessAgent.BaiduNetdisk`、账户 `oauth-client-secret`；经 `launchctl setenv` 设置公开 `HARNESS_BAIDUPAN_CLIENT_ID` 并重启仅本机的 launchd 服务。

脚本不接受 Client Secret 命令行参数、环境变量或文件输入；不打印输入、异常对象、子进程输出或任何凭证；非交互 TTY、格式非法、未确认和任一系统调用失败均拒绝继续。该脚本不打开百度登录页、不读取/下载文件，也不保存 OAuth token。

## 后果

- 用户仍须在百度开放平台创建应用、登记精确回调，并在浏览器中自行登录和授权。
- App Key 是公开标识，供当前 login session 的 launchd 环境使用；用户重新登录后可能须再次运行配置助手，直到另行设计受审查的持久公开配置机制。
- Keychain 写入是用户显式发起的本机动作；配置完成不等于真实 OAuth 或文件数据面已通过验收。
