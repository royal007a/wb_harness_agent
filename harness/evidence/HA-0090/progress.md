# HA-0090 进行中证据

编号说明：初始提交 dfa106a 使用 HA-0080；因并行 DSH 发布已占用该号，客服任务
统一迁至 HA-0090，不覆盖 DSH 证据。旧提交历史保留。

## Provider 原子切片

- `pytest -q tests/test_support_providers.py`：18 passed。
- `pytest -q tests/test_support_providers.py tests/test_workbench.py tests/test_agent_runtime.py`：78 passed。
- 覆盖：AES-GCM 密文与 provider AAD、轮换、无密返回、主密钥缺失/坏权限/符号链接、
  输入/端点拒绝、MockTransport 探测协议、每日限额、鉴权错误脱敏、后台自行发起且
  due 时间阻止重复、取消与编辑互斥、HTTP 明文代理禁止上传凭证。
- 模型/网络均为合成 MockTransport；未读取 Keychain，未部署。
- 本证据不证明课程平台已完成；Agent/流式会话、知识库、工作流、MCP、浏览器、
  真实 Provider、双端发布仍未完成。

## 会话原子切片

- `test_support_chat.py` + Provider + workbench + agent_runtime：93 passed（chat.xml）。
- 真 SSE 解析经 MockTransport 验证：delta、工具参数分片、stop/tools 终态与 usage/DONE。
  缺 usage、EOF、length、停止后继续内容均不发布，账本未知用量冻结；重放不再发请求。
- Agent 配置快照、多轮历史、每次消息独立共享账本、工具权限/Schema/最大轮次、
  断线和工具等待中取消、重启恢复、原子 assistant 提交、终态不被取消覆盖。
- `/support` 页面及原生 JS 已实现，语法检查通过；**尚未浏览器验收**。
- 预算目前为 Ark 模型保守预留完整 1,024,000 输入上限，不将字符估计冒充硬预算。
  小于此预留的消息预算会在发送前拒绝；实际 usage 结算后释放差额。
- 知识库、工作流、MCP、真实 Provider、双部署仍未完成。
