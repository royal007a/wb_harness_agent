# HA-0080 进行中证据

## Provider 原子切片

- `pytest -q tests/test_support_providers.py`：18 passed。
- `pytest -q tests/test_support_providers.py tests/test_workbench.py tests/test_agent_runtime.py`：78 passed。
- 覆盖：AES-GCM 密文与 provider AAD、轮换、无密返回、主密钥缺失/坏权限/符号链接、
  输入/端点拒绝、MockTransport 探测协议、每日限额、鉴权错误脱敏、后台自行发起且
  due 时间阻止重复、取消与编辑互斥、HTTP 明文代理禁止上传凭证。
- 模型/网络均为合成 MockTransport；未读取 Keychain，未部署。
- 本证据不证明课程平台已完成；Agent/流式会话、知识库、工作流、MCP、浏览器、
  真实 Provider、双端发布仍未完成。
