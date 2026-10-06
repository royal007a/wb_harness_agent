# HA-0084 课程资料分批阅读与实现映射

状态：running。基线 5939e5d；worktree harnessagent-dsh-course；分支 dsh/course-hardening-20261006。

## 交付

1. 全目录路径、哈希、页数与重复清单，不复制课程正文。
2. 相关章节全文阅读、关键页核对、逐章总结与具体代码映射；待读不伪装为无关。
3. 每项候选的收益、代价、权限边界与行为验收；运行时实施使用后续独立 HA 编号。
4. 每批固定提交给 mymacclaude 核查课程忠实度、现状判断和验收充分性。

## 当前进度

- 清单183文件/177独立内容/2101页已生成。
- 第一批五篇43页全文阅读及两页渲染检查完成；其余仍待分批阅读。
- 第二批Plan/Replan/长合同五篇55页全文阅读完成，累计十篇98页；见 `docs/research/JIKESUMMARY_PLAN_CONTEXT_2026_10_07.md`。
- 第三批安全四篇/测试两篇42页全文阅读完成，累计十六篇140页；人工审批反例已渲染核对，见 `docs/research/JIKESUMMARY_SAFETY_TESTING_2026_10_07.md`。
- 第四批检索四篇55页全文阅读完成，累计二十篇195页；核对混合检索流程和父级排序图，见 `docs/research/JIKESUMMARY_RETRIEVAL_2026_10_07.md`。原有评测的标注参与排序与单候选限制已重新核对。
- 第五批DSH架构两篇26页全文阅读完成，累计二十二篇221页；固定源码核对发现课程invariant.ts引用已不适用，当前发送前平台组装也不在框架日志重建边界内。见 `docs/research/JIKESUMMARY_DSH_ARCHITECTURE_2026_10_07.md`。
- 第六批工具并发、TAO选择、流式前端三篇37页全文阅读完成，累计二十五篇258页；TAO鉴权图和前端布局图已渲染核对。见 `docs/research/JIKESUMMARY_TOOLS_UI_2026_10_07.md`。不把只读合同工具视为无平台副作用，不把异步点击返回当请求已到达。
- 第七批Benchmark与三层测试两篇20页全文阅读完成，累计二十七篇278页。两条私有无模型探针验证课程评分条件不足，并实测本项目付款评分器的数值/单位和失败Run误计分，拟单列HA-0088修复。见 `docs/research/JIKESUMMARY_EVALUATION_2026_10_07.md`。
- 第八批成本装饰器与Tracing两篇25页全文阅读完成，累计二十九篇303页。核对了Tracing实际计时日志和作者对defer问题的承认；失败不计费、原文预览和币种混用不可照搬。见 `docs/research/JIKESUMMARY_COST_TRACE_2026_10_07.md`。
- 第九批Hooks两篇22页全文阅读完成，累计三十一篇325页；对照SDK 0.2.152核对tool_response/error/defer，渲染格式化命令后确认未引用路径和2>&1解释边界。见 `docs/research/JIKESUMMARY_HOOKS_2026_10_07.md`。
- 第十批Loop Engineering与Provider两篇34页全文阅读完成，累计三十三篇359页；Loop第11–18页图逐页核对。明确计划投影不等于DAG调度、同一接口不等于协议保真，见 `docs/research/JIKESUMMARY_LOOP_PROVIDER_2026_10_07.md`。
- 第十一批生成评审一篇15页全文阅读完成，累计三十四篇374页。区分版本批准、证据字符串与真实事实，核对了正文和grounded代码的差异，见 `docs/research/JIKESUMMARY_REVIEW_VERSIONS_2026_10_07.md`。
- 第十二批阶梯压缩与细节回读两篇29页全文阅读完成，累计三十六篇403页。核对配对、字符阈值、异步索引水位和摘要的权限边界，见 `docs/research/JIKESUMMARY_COMPACTION_RECALL_2026_10_07.md`。
- 第十三批部署容量一篇14页全文阅读完成，累计三十七篇417页。区分用户人数和实际负载、队列和传输、示例数据库规则和平台契约，见 `docs/research/JIKESUMMARY_DEPLOY_CAPACITY_2026_10_07.md`。
- 第十四批交互契约与并发两篇17页全文阅读完成，累计三十九篇434页。核对逻辑调用身份、重放载体、锁生命周期与租约的迟到写入边界，见 `docs/research/JIKESUMMARY_CROSSING_CONCURRENCY_2026_10_07.md`。
- 第十五批TDD与质量体系两篇30页全文阅读完成，累计四十一篇464页。核对未跨窗口的排序反例、正确失败阶段、弱错误断言与独立评分，见 `docs/research/JIKESUMMARY_TEST_ORACLES_2026_10_07.md`。
- 第十六批记忆失效与失败经验两篇25页全文阅读完成，累计四十三篇489页。区分状态与偏好、激活与可信、提醒与执行授权，见 `docs/research/JIKESUMMARY_MEMORY_FAILURES_2026_10_07.md`。
- 第十七批权限与检查点两篇25页全文阅读完成，累计四十五篇514页。核对历史配置与当前官方文档的差异，明确文件回退不撤销账本、数据库与外部副作用，见 `docs/research/JIKESUMMARY_PERMISSION_RECOVERY_2026_10_07.md`。
- 第十八批系统集成一篇11页全文阅读完成，累计四十六篇525页。核对短事务、实体快照、最小披露与固定错误边界，见 `docs/research/JIKESUMMARY_SYSTEM_INTEGRATION_2026_10_07.md`。
- 第十九批工具护栏两篇24页全文阅读完成，累计四十八篇549页。用本地表达式核对域名和目录前缀问题，对照固定Pi源码区分事件改写与实际参数，见 `docs/research/JIKESUMMARY_GUARD_BOUNDARIES_2026_10_07.md`。
- 第二十批工作流存储与执行两篇23页全文阅读完成，累计五十篇572页。核对配置示例与执行契约的差异、变量覆盖和审计失败语义，见 `docs/research/JIKESUMMARY_WORKFLOW_EXECUTION_2026_10_07.md`。
- 第二十一批MCP接口两篇23页全文阅读完成，累计五十二篇595页。区分工具发现与授权、调试与真实副作用，并核对官方2025/2026协议生命周期差异，见 `docs/research/JIKESUMMARY_MCP_BOUNDARIES_2026_10_07.md`。没有启用MCP插件。
- 第二十二批RAG入库两篇25页全文阅读完成，累计五十四篇620页。核对两库异步处理、删除后迟到写入和作者承认的绑定缺口，见 `docs/research/JIKESUMMARY_RAG_PIPELINE_2026_10_07.md`。没有新增Embedding或存储依赖。
- 第二十三批规范与执行两篇24页全文阅读完成，累计五十六篇644页。核对任务计数、TDD编号和已批准方案与执行指令的矛盾，见 `docs/research/JIKESUMMARY_SPEC_EXECUTION_2026_10_07.md`。不把商业Harness平台混作本项目。
- 第二十四批最小Runtime与反思两篇30页全文阅读完成，累计五十八篇674页。对照固定Pi源码核对依赖与监听语义，区分固定批评器演示与真实纠错，见 `docs/research/JIKESUMMARY_RUNTIME_REFLECTION_2026_10_07.md`。
- 第二十五批对话引擎两篇16页全文阅读完成，累计六十篇690页。核对传输、持久成功、双写和窗口条数的边界，并区分当前聊天与DSH路径，见 `docs/research/JIKESUMMARY_CHAT_TRANSPORT_2026_10_07.md`。
- 本研究任务不修改运行时、不部署、不调用真实 Provider；HA-0085/0086 是分开的实现任务，不能混算研究验收。

## 非目标

不把183份的目录盘点当精读；不上传课程全文；不自动引入新引擎、K8s、遥测外发、MCP或凭据；不把研究批准当部署批准。
