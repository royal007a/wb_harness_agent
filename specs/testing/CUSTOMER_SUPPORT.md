# 智能客服平台验收合同

状态：实现中，不是现有能力清单。

1. Provider/Model 可创建、修改、停用、删除；Key 写入数据库密文，列表/详情不回显。
   密钥轮换有效，旧密文不可跨 Provider 替换；主密钥缺失、权限错误、损坏拒绝。
2. 自动联网探测由生命周期管理，启用的记录按持久 due 时间调度。手工/自动互斥，
   日限额合计；关闭 Provider 后不再发送。错误不携带秘密；重启不重置每日限额。
3. Agent 固定模型、system prompt、工具、知识库/工作流配置；显式能力无隐式换引擎。
4. 持久 Session、user/assistant、Exchange；真实 POST SSE、多轮上下文、取消/超时、
   幂等与单会话并发拒绝。失败不发 done、不持久不完整 assistant；重启终结遗留调用。
5. TXT 上传、结构切块、来源引用、检索与回答集成；区分词法与向量检索，不将前者
   冒充后者。向量模式须真实 embedding、维度/模型绑定、受控召回与删除失效。
6. JSON 工作流支持顺序和条件分支、输入校验、循环上限/取消、逐节点可观测结果。
7. MCP 配置、工具发现与调用、Agent 权限绑定；不开放任意 shell/host 文件。
8. 管理 UI 包括上述模块，390px 可用，无 innerHTML 用户内容，切换会话无旧响应污染。
9. 离线反例、真实模型公开 FAQ、浏览器与重启持久验证；先8765后132，固定版本和
   受认证代理验证。仅服务200不等于业务验收。

## Provider API v1（HA-0090 第一原子切片）

`GET/POST /api/local/support/providers`，`PUT/DELETE .../providers/{id}`，
`POST .../providers/{id}/probe`，`GET .../status`。
写对象字段：name、base_url、model、api_key（创建必填，更新省略保留）、enabled、
auto_probe、probe_interval_seconds（300–86400）。未知字段拒绝，字符串和集合有界。
输出不含 api_key/ciphertext，仅 has_key。错误沿用 Problem 信封。
编辑/删除与探测通过同一 provider 租约互斥；探测开始时先原子登记日计数和下一时间。

## 会话 API v1

Agent CRUD：`GET/POST /agents`、`PUT/DELETE /agents/{id}`。字段 name、provider_id、
model、system_prompt、enabled、tools、knowledge_ids、workflow_ids、mcp_ids，以及
max_turns(1..8)、max_output_tokens(32..8192)、token_budget(1..20000000)、
timeout_seconds(5..300)、context_turns(1..20)。未注册工具不可配置。
Session：`GET/POST /sessions`、`GET/DELETE /sessions/{id}`。创建时快照 Agent 配置，
运行前重查当前 Agent/Provider 仍启用，删除活跃会话拒绝。
`POST /sessions/{id}/messages` 使用 Idempotency-Key，body={content}；SSE
为 start/delta/tool/done/error。delta 为未提交预览，done 只在完整协议、用量结算、
事务提交成功后发送。`POST /exchanges/{id}/cancel` 取消指定会话执行。
相同 key 重放终态不再调用 Provider；异 key 在 busy 时409。断线取消，不自动续模型。
每次真实请求先走 HA-0075 预留与结算；上下文有界，缺 usage 冻结而非当0。
Ark 可在终止 choice 和紧随的空 choices 帧重复相同 usage；只允许这个精确组合、
内容逐值一致且只结算一次。冲突、提前或多次 usage 仍拒绝；不保留 reasoning_content。
Ark 请求显式关闭 thinking，并用 max_completion_tokens 限制回答与思考的总输出；
不能用只限制回答的 max_tokens 冒充账本的总输出上限。账本仍校验实报 usage，超限失败。
重启将 queued/running 标为 failed/SUPPORT_RESTARTED；完整历史仍可读取。

## 知识库 API v1（第三原子切片）

`GET/POST /knowledge`、`PUT/DELETE /knowledge/{id}` 管理名称、说明、enabled。
`POST /knowledge/{id}/documents` 接收 JSON `{name,text}`（TXT/MD，UTF-8，最多10万字符）；
文件字节由前端读取，后台仅保存规范化文本，不开放服务器文件路径。返回202，持久
processing 状态，后台生成全部向量后原子提交 ready；失败或重启明确 failed，无半份索引。
`GET /knowledge/{id}` 含文档元信息；`GET/DELETE /documents/{id}` 查看分块或删除。
`POST /knowledge/{id}/search` 接收 `{query,top_k,min_score}`；跨库只检索 Agent 显式绑定集合。

采用固定 BAAI/bge-small-zh-v1.5（512维）本地 ONNX 语义向量，模型部署时预下载并
登记固定修订，运行时离线加载，不自动联网下载、不发送知识正文到 Embedding 服务。
语义索引存在 SQLite 并做归一化余弦排序，适用小型客服知识库，不声称 ANN/pgvector规模。
结构切块复用父子文档 helper；子块最多400字符，父块最多2000字符，单文档至多256子块，
全库至多4000子块。文本与偏移对齐；子块召回扩展至去重父上下文，总注入不超过8000字符。
查询无命中仍显式告诉模型资料不足，不伪造答案。分数阈值是可配置策略，不是相关性保证。
知识库未绑定时不触发检索。RAG来源元信息随 Exchange 保留，不保存重复的检索正文；
正文作为不可信参考数据，不授予工具权限。删除/禁用在检索提交和回答发布前重新检查。
运行时向量进程有独立时间/输出/并发上限，取消时杀掉并等待退出；模型调用仍用同一账本。
PDF 导入、扫描OCR和大规模向量数据库不在此原子切片里；整体后续是否支持另记证据。

## 工作流 API v1

`GET/POST /workflows`、`GET/PUT/DELETE /workflows/{id}`，字段 name、description、
enabled、nodes、edges。JSON 编辑界面，不承诺拖拽画布。节点类型 START、LLM、CONDITION、
KNOWLEDGE、TOOL、END；每个节点 id/type/config，边 source/target/condition（null或boolean）。
配置保存前校验节点唯一、唯一START、可达END、边完整、分支true/false完整、无环，至多32节点。
运行时仍有32步上限；变量仅 `{{节点.output}}` 与 `{{start.input}}`，单次替换、无eval、
未知变量拒绝，节点只写自己的输出；池和单节点输出有界。

Agent 至多绑定一个工作流，创建会话时冻结工作流定义；停用/删除或版本变化则拒绝执行。
绑定后消息走工作流，不再并行走普通聊天；未绑定的旧聊天/RAG不变。
LLM 节点仅用 Agent 已配置 Provider/模型，经过同一 HA75 账本和调用次数/截止时间限制，
不偷偷附带工具或自动重试。KNOWLEDGE 只检索 Agent 绑定库，TOOL 只调用 Agent 已准入工具，
无任意 HTTP/代码节点；课程 API_CALL 用已注册工具替代，MCP 工具仍须审批规则。
事件推送节点状态，最终 END 输出才是用户回答；中间分类文本不直接当成答案。
`GET /workflows/{id}/runs` 返回整轮/节点状态、耗时、输出哈希/长度和固定错误码，不存完整变量池。
工作流成功与最终 assistant 在同一事务提交；失败、取消、重启均为明确终态，不自动重跑。
验收包括线性、双分支、知识检索/工具、缺变量、环/坏边、节点错误、共同预算耗尽、取消、重放不外发。

## MCP 与合成退款演示

`GET/POST /mcp`、`PUT/DELETE /mcp/{id}`、`POST /mcp/{id}/discover`、
`POST /mcp/{id}/debug`；配置 name/endpoint/enabled/read_only_tools。端点必须在部署
精确允许集合内，无 stdio/shell，禁止重定向、压缩和继承代理；官方 MCP 2.2.0
Streamable HTTP 客户端完成 initialize/tools/list/tools/call。发现不是模型调用。
远端工具 Schema 有界且禁止外部引用；Agent 同时绑定 Server 和具体工具名，会话冻结
Server 配置版本，停用或变化后拒绝。只读属性由管理员显式指定，不采信服务端注解。

非只读工具只创建待确认动作，模型不拥有确认接口。`GET /approvals` 与
`POST /approvals/{id}/decision`（approve/reject），绑定工具、参数、配置、会话，10分钟有效；
会话动作必须等 Exchange 成功后才能确认，失败/取消不执行。重复确认返回原收据。
超时或崩溃后 executing 变 unknown，不自动重试外部写入。审批记录保留供审计。

内置合成退款 MCP 用官方 Server，经真实 loopback HTTP 调用；与平台同进程，不称独立部署。
每次服务启动生成仅内存 Bearer 能力令牌，公网/浏览器无令牌不能直接调用它。
SQLite 合成订单与退款记录支持资格查询、申请、状态查询、取消；签收7天以内、
重复申请禁止、只有 pending 可取消。写工具还在业务侧核对已批准动作，模型不能传入
approval_id 冒充批准。工具结果只代表演示记录变更，绝不调用银行/支付或真实退款。
UI 包含配置、发现、JSON工具调试、审批和演示订单；所有结果按不可信文本展示。
