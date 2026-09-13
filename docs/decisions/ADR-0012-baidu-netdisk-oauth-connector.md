# ADR-0012：百度网盘 OAuth 连接器（本地受控准备）

- 状态：Accepted（本地 OAuth 连接准备）
- 日期：2026-09-13
- 触发：用户选择 P2 官方 OAuth 连接器；不授权分享链接爬虫、Cookie 复用或验证码绕过。

## 背景

用户需要把百度网盘内已授权资料导入本地阅读流程。浏览器分享页不能作为稳定、可审计的服务接口；它可能要求登录、验证码或客户端下载。百度开放平台公开提供账号授权、文件管理和内容传输能力，但接入需要注册应用及用户授权。

## 决策

本地工作台增加一个仅绑定 `127.0.0.1` 的授权码 OAuth 连接器，固定向 `https://openapi.baidu.com` 发起授权和令牌请求。授权请求使用 `basic,netdisk` scope、随机 state、固定回调 URI；state 只保存摘要和短期状态。Client Secret、access token 与 refresh token 不写入 SQLite、日志、事件、产物、Evidence 或仓库；连接器从 macOS Keychain 读取/写入受限凭证。

第一切片仅验证连接、授权回调、令牌交换、刷新和断开授权的边界。网盘目录、下载、分享链接和文档解析在 OAuth 连通、官方文件 API 版本/范围核验及数据保留策略确认前不开放。

## 后果

- 用户必须在开放平台创建应用，登记精确回调地址，并由本人完成百度登录/授权。
- 环境仅保存公开 Client ID 与回调地址；Keychain 中由用户建立 Client Secret 条目。真实 token 只在回调/刷新处理的短暂内存中存在。
- 回调允许唯一的跨站 `GET` 入口，其余本地 API 仍拒绝跨站请求；state 一次性、十分钟失效。
- 单用户本地版本不等同多租户 OAuth 服务；对外绑定、共享凭证或自动审批须另行 L3 审查。

## 来源

[百度 OAuth 接入指南](https://openauth.baidu.com/doc/doc.html)、[百度网盘开放平台](https://yun.baidu.com/open/platform)，核验日期 2026-09-13。实际文件 API 以用户应用开通后可见的官方版本为准。
