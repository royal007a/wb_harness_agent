# ADR-0014：百度网盘分享链接的官方客户端交接 Skill

- 状态：Accepted（本地客户端交接）
- 日期：2026-09-13
- 触发：用户要求从聊天中的明确百度网盘分享链接下载资料，并同步能力到 Claude。

## 决策

项目内增加 `skills/baidu-netdisk-download/`，并以符号链接同步到 `~/.claude/skills/baidu-netdisk-download`。Skill 只接受当前用户消息或明确引用消息里的 `https://pan.baidu.com/s/...` 链接；脚本从标准输入读取该链接、只启动固定 macOS 官方客户端 `/Applications/BaiduNetdisk_mac.app`，返回链接 SHA-256 摘要而非原链接或 `pwd`。

用户必须在官方客户端内自行登录、确认提取码、选择保存位置和开始下载。下载后，Skill 仅可校验用户明确提供的 `~/Downloads` 下普通非符号链接文件路径；它不读取文件内容，也不移动、删除或上传文件。

## 后果

- 不使用浏览器自动化、Cookie/会话复用、验证码处理、网页抓取、反编译协议或未核验的 PCS/直链 API。
- 这不是 HA-0010/0011 OAuth 数据面能力的放开；目录、直接下载、分享链接导入、预览和内容解析继续受 TD-020 的独立审批和验收约束。
- Claude 的同步采用可追溯符号链接，项目中的 Skill 变更即时生效；不复制敏感信息到个人配置目录。
