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

## Provider API v1（HA-0080 第一原子切片）

`GET/POST /api/local/support/providers`，`PUT/DELETE .../providers/{id}`，
`POST .../providers/{id}/probe`，`GET .../status`。
写对象字段：name、base_url、model、api_key（创建必填，更新省略保留）、enabled、
auto_probe、probe_interval_seconds（300–86400）。未知字段拒绝，字符串和集合有界。
输出不含 api_key/ciphertext，仅 has_key。错误沿用 Problem 信封。
编辑/删除与探测通过同一 provider 租约互斥；探测开始时先原子登记日计数和下一时间。
