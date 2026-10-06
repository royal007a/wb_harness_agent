# DSH 合同审查：jikesummary 对照加固切片（mymacclaude，分支 dsh/claude-hardening-20261007）

每个切片都单独提交，并附反例和单点突变。“已审”只限代码与离线行为，全量门禁、8876 部署和真实 Provider 验收另行进行。

| 任务 | 提交 | 契约 | 不承诺 | 状态 |
|---|---|---|---|---|
| HA-0093 | 50f6f41 | `backend/sensitive_patterns.CREDENTIAL_SHAPE` 是凭据样式检测的唯一定义；DSH 文档中出现 `password=` 返回 422 | 不做 PII 拦截或脱敏 | 待审 |
| HA-0094 | 3dd3ca2 | 不含证据块的工具结果不存根；最后一次提交未通过时，可信状态带错误码 | 含 matches 加 notice 的结果仍可能被存根 | Approved（离线） |
| HA-0095 | d2a787f | `run.failed.failure_point`：先按固定错误码映射，其次取 blocked 步骤，最后取最早未完成步骤；`failed_step` 含义不变 | 归因提示，不是根因 | Approved（离线） |
| HA-0096 | 88899d7 | 非 unknown 槽位引文的来源块命中 `INSTRUCTION_MARKERS` 时，追加缺口 `QUOTE_SOURCE_HAS_INSTRUCTION_MARKERS` | 只覆盖现有正则；不阻断、不隔离；不是防注入 | Approved（离线） |
| HA-0097/0098 | e32fc03 | 模型、工具事件带整数 `latency_ms`；free 模板发布时写 `dsh.output.scanned`（影子模式，只记计数） | 不改变发布内容；不是 Trace 树 | 待审 |
| HA-0099 | 57d12ee | 格式正确但不存在的 clause 编号返回带提示的观察，每 Run 最多 2 次 | 格式错误和越权仍然硬失败 | 候选，收敛期不审 |
| HA-0110 | 86b030a | 检索按 NFKC、去空白、casefold 比较；全空白查询返回 DSH_TOOL_INPUT | 不是同义词扩展 | 候选 |
| HA-0111 | 8591710 | 单主体结论的数值，最近的前置主体不是该主体时，追加缺口 `CLAIM_PARTY_VALUE_UNBOUND` | 启发式，只提示 | 候选 |
| HA-0112 | 97bd642 | 插件 TOOLS 声明与平台检查、SEARCH_PAGE、contextWindow 的漂移测试 | 只是测试 | 候选 |
| HA-0113 | d789fc3 | 首次模型请求前写 `dsh.run.versions`；`run.succeeded.versions` | 摘要不能重建请求 | 候选 |
| HA-0114 | ea1d55c | `GET /api/local/dsh/runs/{id}/trace`：按轮次的只读元数据投影 | 不重建请求，没有前端 | 候选 |
| HA-0115 | 3b89afe | 未读例外候选与未读付款块两类缺口同时上报 | 无 | 候选 |
