# ADR-0080：课程智能客服平台及数据库凭证

状态：Accepted for implementation，2026-10-06 用户明确要求；尚未验收。

## 决策与原规则的冲突

用户要求两小时内实现课程智能客服、API Key 入库、后台自动联网探测并重新部署。
这显式替代 ADR-0021/0022 在**新客服模块**中「仅凭证引用、禁止后台探测」的限制，
不自动开启旧 Agent Lab、Native、Pi、DSH 或 Memory semantic 的门禁。

保留 FastAPI/SQLite/原生前端。新增 `/support` 和 `/api/local/support/*`，与
Product Task/Run 和既有聊天表隔离；是受信单管理员平台，不声称多租户隔离。
课程来源：`Claude Code 企业级全链路开发实战` 产品定义及 13、15–18、20–25 讲。
全目标包括 Provider/Model、Agent、持久流式聊天、TXT 知识库与 RAG、JSON 工作流、
MCP 和管理界面；凭证小切片完成不代表整个目标完成。

## 安全边界

- API Key 用 AES-256-GCM 密文存 SQLite；随机 96-bit nonce，provider ID 作 AAD。
  密文列不进通用 JSON、审计或幂等收据，HTTP 只写不读；主密钥单独 0600 文件，
  部署持有，不进 Git、DB、环境值、日志。丢失主密钥时拒绝解密，不自动替换。
- 仅管理员明确登记的 HTTPS 精确 Base URL 可出站；默认只允许用户指定的 Ark
  coding/v3。拒绝重定向、代理环境继承、URL 凭证/参数/片段；响应大小/超时有上限。
- 每个 Provider 可启停自动探测；默认每 900 秒，一次最多 32 输出 token，不重试，
  每 provider 每 UTC 日至多 96 次（手工与后台合计）。探测发送固定公开文本，
  不发送会话/知识库；成功只表示该次调用成功，非业务质量或供应商兼容性保证。
- 探测状态只保存固定错误码、时间、耗时、用量；不保存上游正文/异常/响应头。
- HTTP 公网入口不具备传输加密：凭证写入只允许直连 loopback/SSH 隧道或可信
  nginx 声明的 HTTPS；远端首次凭证通过 SSH 受控导入，不在明文网页提交。
- 本机先 8765、再 132；备份实际 DB、保留运行时目录、记录固定版本。DSH 8876 不动。

## 验收

见 `specs/testing/CUSTOMER_SUPPORT.md` 与 HA-0080 计划。加密接口依据
[cryptography AEAD 文档](https://cryptography.io/en/latest/hazmat/primitives/aead/)。
