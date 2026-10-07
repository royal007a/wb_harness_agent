# 研究包两组官方在线引用补核

核对日期：2026-10-07（Asia/Shanghai）。对象为 da43bff 的 MCP_BOUNDARIES 和 PERMISSION_RECOVERY 两份报告。此记录由 Codex 执行方补查，不冒充 Claude 的独立联网复核，也不扩展其 PDF 抽查范围。

## MCP 协议版本

2026-07-28 公告确实发布于官方 MCP 博客。其中 “No handshake or sessions” 明确移除了 initialize/initialized 交换和 Mcp-Session-Id，并引入非强制的 server/discover。报告区分新旧协议生命周期的判断得到支持；无状态协议核心不等于业务不能自行持有状态。[官方版本公告](https://blog.modelcontextprotocol.io/posts/2026-07-28/#no-handshake-or-sessions)

旧版引用页面也可访问，分别为固定 2025-11-25 版本的 [Lifecycle](https://modelcontextprotocol.io/specification/2025-11-25/basic/lifecycle) 和 [Transports](https://modelcontextprotocol.io/specification/2025-11-25/basic/transports)。没有安装 MCP SDK 或执行协议探针，不声称项目已接入新版本。

## Claude Code 权限与沙箱

当前官方权限页的 “Manage permissions” 明确顺序为 deny → ask → allow，规则具体程度不改变这一次序。MCP 的 allow 通配规则必须具有固定的 server 前缀；不能把“支持通配”理解成任意全局通配都会放行。[官方权限说明](https://code.claude.com/docs/en/permissions#manage-permissions)

当前沙箱页支持报告的范围区分：限制对象是 shell 命令及其子进程，文件工具、MCP、Hooks 不被这个边界统一包住；默认读范围较宽，环境变量也会继承。failIfUnavailable 控制依赖缺失或不支持时是否拒绝启动；allowUnsandboxedCommands 控制非沙箱重试。单独关闭后者不等于任何路径都被隔离，excludedCommands 等仍需审计。[官方沙箱说明](https://code.claude.com/docs/en/sandboxing)

检查点页同时明确 Bash 改动与外部编辑的限制，并将检查点和长期版本控制区分开。报告没有把文件回退写成数据库、外部动作或计费的回滚，这个边界成立。[官方检查点说明](https://code.claude.com/docs/en/checkpointing#limitations)

## 证据边界

这是官方在线文档的访问时点核验，不是固定版本 CLI 的行为测试。报告已将课程界面的 v2.0.24、项目锁定 SDK/CLI 和当前官方网页分开；本次不修改依赖、设置、权限或运行服务，也不宣称这些选项已经在 HarnessAgent 中启用。官方网页会更新，未来实施仍须固定目标运行版本并做反例。
