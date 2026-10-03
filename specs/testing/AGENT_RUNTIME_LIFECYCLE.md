# Agent Runtime 生命周期测试规格（HA-0054）

契约依据：ADR-0054、agent-runtime.schema.json；实现以测试结果为准。

| 场景 | 必须成立 |
|---|---|
| queued 先 cancel 再 stream | 0 凭证解析/Provider 请求，cancelled 不变，error=EXCHANGE_CANCELLED |
| streaming 两个消费者 | 仅 owner 调用一次，重复方 EXCHANGE_IN_PROGRESS，owner 不被取消 |
| 同 Session 新键并发发送 | SESSION_BUSY，用户消息数不变，原键可重放 |
| 首 delta 后取消 | 后续无 delta/done，关闭上游，无 assistant，持久 cancelled |
| Provider 正在等待时取消 | 不依赖下一 delta，轮询取消在有界时间内释放上游 |
| owner generator aclose / task.cancel / HTTP disconnect | 关闭上游，非终态转 cancelled，不伪造回答 |
| 非 owner disconnect | owner 不受影响 |
| 已 succeeded/failed/cancelled 重放 | 状态/消息数/调用数不变，错误计数来自历史 |
| Provider 抛错/空结果/超时/超长 | 稳定错误码，部分输出不入 assistant |
| 重启（含 worker 关闭） | 活动 Exchange 变 MODEL_RUNTIME_RESTARTED；终态不变；0 网络 |
| 上下文/隔离 | 只取当前 user 序号之前最多 2N 条，不改变 Product Task/Run |

验证层：临时库、合成 Adapter、HTTP/ASGI SSE；不使用真实凭证或 Provider。
命令：`.venv/bin/python -m pytest -q tests/test_agent_runtime_lifecycle.py tests/test_agent_runtime.py tests/test_workbench.py`。
