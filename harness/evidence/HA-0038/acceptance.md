# HA-0038 发布与验收记录

状态：accepted（本机受限协作控制面）。

## 已交付

- `team-attention@1` 固化了不含正文的 Conversation sequence、Attention item、Read cursor、Work mark 与 Attention lease。
- 所有 ingress、Inbox、读取与 Item 写路径均复用 Workspace / Channel / membership / clearance 边界；`source_ref` 为非 URL 的 opaque metadata，不可承载正文或附件。
- 同一 protocol identity 一次只能持有一个 Attention lease；lease 过期会释放 Item 并恢复 `open` work mark，不会把未处理的工作误清除。
- 在同一个 SQLite 事务中，新 Thread sequence 会拒绝旧 Attention completion、Team Task Handoff、submit 和 Gate；调用方必须补读、重写或停止旧决定。

## 验证证据

- 定向 Attention / Team Task / Foundation 回归：16 passed。
- 完整回归：240 passed、12 skipped、0 failed；见 `all-tests.xml`。
- Harness 验证与 Team Attention 合成评测通过；metadata 顺序、单租约、过期 completion 阻断、work mark、Task Handoff freshness 和零外部执行均为 1.0；见 `team-attention-evaluation.json`。
- 本机 launchd 与公网 systemd/nginx 都已发布并校验 health、Attention runtime、OpenAPI 和未认证边界。远端在 promotion 前从运行中的 systemd 解析实际数据库，Python SQLite online backup 和完整性检查通过；关键文件 SHA-256 与本地相同。详见 `deployment.json`。

## 发布过程修正

- 首次远端备份命令假定 `sqlite3` CLI 可用，目标主机并未安装该 CLI；该命令在任何 promotion 前失败，未修改运行代码或数据库。
- 随后仍从运行服务解析实际 `HARNESS_DB`，在批准数据根目录内使用 Python 标准库的 SQLite online-backup API 生成备份并确认 `integrity_check=ok`，之后才执行 promotion 和重启。

## 不代表

真实 HTTP 身份认证、OIDC/token、消息/Thread/DM 正文或附件、飞书/Slack 接入、通知、WebSocket、自动唤醒、自动委派、Agent Runtime、Daemon/Computer、Session、模型、Provider、MCP、工具、网络、真实投研或真实权限执行均未实现或放行。
