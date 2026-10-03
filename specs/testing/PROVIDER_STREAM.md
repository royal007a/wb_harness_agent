# Provider 流完整性（HA-0057）

范围：当前 text-only、单 choice 的 OpenAI-compatible Chat Completions Adapter。
不增加工具、模型准入、重试、Provider fallback、费用保证或 Product Run 集成。

## 成功契约

- HTTP 成功且 Content-Type 为 text/event-stream（可带参数）。
- SSE 按空行组帧，支持 UTF-8/BOM、LF/CRLF/CR、跨网络块和多行 data；注释与
  非 data 字段不进入文本。未完整分隔的最后一帧不得因 EOF 自动当成成功。
- JSON 帧是 chat.completion.chunk 对象，非空 id 在同一响应内保持一致；唯一
  choice 的 index=0，delta 是对象，content 为 string/null，role 若提供须 assistant。
  重复 JSON 键与 NaN/Infinity 拒绝，避免歧义终止字段掩盖截断或错误。
- 正常终止必须先收到 finish_reason=stop，再收到完整 data: [DONE] 帧。
  stop 帧可携带最后文本；之后只接受一个可选的 choices=[]、usage 对象元数据帧。
  DONE 后立即关闭上游，不等待也不发布尾随字节；usage 不代表已实现费用账本。
- Adapter 正常结束仅表示协议完整；Runtime 仍检查非空、12000 字符上限和取消状态，
  仅成功时事务性写入 assistant+succeeded。失败期间预览不是交付。

## 错误分类

| 输入 | 持久错误码 |
|---|---|
| delta/stop 后 EOF，或未先 stop 就 DONE | MODEL_PROVIDER_INCOMPLETE_STREAM |
| finish_reason=length | MODEL_OUTPUT_TRUNCATED |
| content_filter | MODEL_PROVIDER_FILTERED |
| tool_calls/function_call 或工具 delta | MODEL_PROVIDER_UNSUPPORTED_OUTPUT |
| refusal 非空 | MODEL_PROVIDER_REFUSED |
| 上游 error 对象或非 2xx | MODEL_PROVIDER_REJECTED |
| Content-Type/JSON/choice/delta/id/终止顺序不合法 | MODEL_PROVIDER_INVALID_RESPONSE |
| 解码后流字节超过 2 MiB，或一帧超过 256 Ki 字符 | MODEL_PROVIDER_RESPONSE_LIMIT |
| 传输超时/HTTP 传输异常 | 保留 MODEL_PROVIDER_TIMEOUT / MODEL_PROVIDER_UNAVAILABLE |

不把上游 error 文本、请求 Authorization 或凭据放进 SSE/持久消息。任何失败都
没有 done 或 assistant；重放失败 Exchange 不再次解析凭据或访问 Provider。
取消应关闭 response/client，不会因为稍后到达 stop/DONE 改成成功。

## 验证

固定 MockTransport + 临时 SQLite：协议矩阵、逐字节 UTF-8/CRLF 分片、多行 data、
正常 usage、格式损坏、所有 finish reason、上游错误、类型/身份漂移、超限、关闭；
真实 Adapter → Runtime 持久化 → 幂等重放；HTTP SSE 同一路径验证失败与唯一成功。
真实 Provider/Keychain/生产库调用均为零。全量及 tests/test_workbench.py 回归。
旧 ce490c5 的 EOF/length 反例必须行为失败；文档协议加强不是第三方 Provider
兼容性验收，未实测的服务不能宣称可用。
