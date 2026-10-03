# ADR-0057：协议完整后才允许发布模型回答

状态：85fc7d3 和压缩响应追加修复 986ed1d 均已独立代码 Approved，双端未部署；真实模型门禁不变。任务 HA-0057，缺陷 PROVIDER-01。

## 证据与选择

ce490c5 的 Adapter 会把普通 EOF 当作正常生成结束，并忽略 finish_reason。
因此即使只有一个 delta 或 length 截断，Exchange 也会写 succeeded 与 assistant。
协议判定应归 Adapter，事务与终态仍归 Runtime/Store；不修改二者接口形状。

使用 OpenAI Docs 核对：官方将 stop、length、content_filter、tool_calls 区分；
每个流的 id 一致，usage 最后一帧可为空 choices。
[Streaming events](https://developers.openai.com/api/reference/resources/chat/subresources/completions/streaming-events)。
官方示例的正常流先 stop，再 [DONE]。
[Create chat completion](https://developers.openai.com/api/reference/python/resources/chat/subresources/completions/methods/create)。
读取日期 2026-10-04。我们选择同时要求二者，是本项目窄协议的 fail-closed 决策，
不是断言所有自称 OpenAI-compatible 的第三方都已通过该契约。

## 后果

采用有界 SSE 组帧和显式成功终止，细则与错误码见
[PROVIDER_STREAM](../../specs/testing/PROVIDER_STREAM.md)。stop 与 DONE 不齐全时
即使已有可读文本也只保留临时预览。工具调用、拒绝、截断均不能伪装为普通回答。
新错误码沿用现有 error_code 字符串契约；没有 Schema 迁移或数据库迁移。
不引入自动重试、不更换引擎、不恢复半段回答、不开放模型调用。

## 复审追加：不接受内容编码

复审证据指出 HTTPX `aiter_bytes()` 会先解压，再进入我们的字节上限检查。
选择请求 identity，拒绝一切 Content-Encoding 响应，再通过 `aiter_raw()` 读取。
不增加一套压缩解码器或依赖；编码存在即失败，即使值是 identity/空值也不例外。
这会拒绝无视协商继续压缩的第三方端点，是显式的窄兼容边界，不静默重试。
