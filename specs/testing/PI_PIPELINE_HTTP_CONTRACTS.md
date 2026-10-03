# Pi 离线管线 HTTP 与 SSE 合同（HA-0067）

基线 5429c62。本项只覆盖 `/api/local/pi/runtime` 的 GET，以及
`/api/local/pi-contract-pipeline/{preview,review,security-check,review-stream}`
四个 POST，不包含 Pi Product Run 的五个列表/创建/详情/events/Gate 入口。

## 当前行为与验收

1. runtime 是准入档案投影，不启动 Pi、不解析凭据。三种状态是 not_admitted、
   approved_for_l3_probe、invalid_not_admitted；模型/外部调用字段恒为 0，
   不是实际调用计数器。损坏或缺失档案仍返回 200 的关闭状态。
2. preview/review 读取已登记 Public PDF。preview 是解析/分类/分块/敏感模式的
   确定性结果，review 始终是 needs_human 候选，不是法律判断或 Gate 通过。
   HTTP 入口只投影 resource_id/chunk_max_chars，额外字段被忽略，不进入摘要
   或幂等 digest；内部 request Schema 仍拒绝额外字段，另设 HTTP request 契约。
3. security-check 评估调用方提交的 action/policy，仅返回 allow/deny 与原因。
   allow 不授予运行权限，provider_admitted=true 也不会改准入档案或执行工具。
   请求严格拒绝额外字段；输出不回显 content/path/url 等输入。
4. review-stream 实际媒体类型为 text/event-stream，而不是 application/json。
   每帧为 `data: <JSON>\n\n`，JSON 是 event/data 对象，顺序固定
   preview → finding → done。三个 data 分别绑定预览、候选、零调用结束对象。
   stream 预览 heading 改为 chunk-N，不发布合同原文。done 仅表示三帧发送结束，
   不表示正式交付。整条流先计算结果，再发送；不是逐 Token 模型输出。
   经过公共中间件后的实际响应为 Cache-Control: no-store（覆盖处理器的
   no-cache），X-Accel-Buffering: no；以最终 HTTP 响应为准。
5. 缺 Accept 或不含 text/event-stream 返回 406 JSON。现实现为区分大小写的
   子串检查（不是完整 Accept 协商，连 q=0 也会通过），文档如实描述，不据此
   宣称媒体协商合规。异常发生在开始流之前，走现有 JSON 错误信封。
6. 三个普通 POST 的 Idempotency-Key 为 1–128 字符；流端点因附加 :preview
   与 :review，当前原始 key 有效范围为 1–120 字符。121 及以上拒绝；不更改
   已持久 key 编码。相同 key 和有效请求重放相同结果且不新增写入；改有效
   请求返回 409。流有两个独立幂等事务，不承诺两份收据原子提交。
7. 源、静态、动态三份契约拒绝空对象、缺字段、多字段、错误阶段 data、
   非零调用和损坏枚举；现有错误信封是 local_http_error。

## 测试与证据

真实 TestClient + 临时 SQLite + 生成 PDF；覆盖敏感与普通 PDF、大小边界、
幂等重放和冲突、请求投影、错误媒体类型、实际三帧顺序/引用/脱敏；
runtime 用临时档案覆盖默认/损坏/批准状态。哨兵禁止执行 Run、启动 sidecar、
解析凭据或调用 Provider。对成功的 GET 和重放比较 total_changes 及 DB 快照。
冻结最终测试回基线，明确是行为失败还是脚手架错误；关键约束做定向突变。

边界：不修改业务执行、无新网络/模型准入，不证明敏感检测没有漏报，不验证
真实 socket 背压/断线，也不增加响应运行时拦截器。双部署仍待本机拓扑批准，
不能跳过本机先发 132。Pi Product Run 与其他空响应合同另行处理。
