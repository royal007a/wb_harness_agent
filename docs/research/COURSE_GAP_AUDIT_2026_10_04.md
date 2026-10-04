# 课程对照：已实现、未贯通与下一步缺口

日期：2026-10-04。审计基线：HarnessAgent `31a1877`；独立项目 `pi-contract-review` `21f9451`（实现修复 `8242f86`）。本报告待 mymacclaude 独立 review。

## 结论先行

**当前强项是控制面、确定性边界与离线验证；最明显的欠缺是把真实业务 Agent 的运行闭环接到同一个 Product Run 上。** 不应把“有聊天、有工具、有沙箱、有 Memory”相加，就说课程里的业务 Agent 已完整落地。

同时，不能说“Pi 合同审查完全没做”：另一个仓库已有真实 SDK 会话、长合同流水线、Web/TUI、人工审批与知识归位。缺的是它与本平台的正式集成和对应验收，不宜重复开发同一套。

本报告是功能差距分析，不是漏洞审核或新开发授权。P0/P1/P2 表示建议的交付优先级，不表示安全严重度。不开 Provider/语义检索/外部工具门禁，不实施认证，不修改运行时，不部署。

## 1. 来源与阅读范围

课程目录：`/Users/weberzhao/Downloads/Harness Agent 脚手架实战课`。

- 盘点 27 份 PDF 并提取文本、建立主题索引；包含目录、开篇、直播、正文、加餐、结语、测试介绍。文件大小与 SHA-256 见同目录 `COURSE_GAP_AUDIT_2026_10_04.sources.json`。
- `09 - 07 | …` 与 `09 - 07 ／ …` 为同一标题的两份不同 PDF，按一个能力主题处理，不算两门课。
- 重点阅读代码闭环、Session/Fork、Hooks、OTel、Wiki、Pi 分层/长上下文/护栏等机制页；另渲染检查文件 20 的 PDF 第 3 页护栏流程图。**不是每页截图和评论都精读过。**
- 下表文件编号是文件名前缀，和标题里的课号不同。例如文件 17–22 对应标题 15–20。
- 结课测试 PDF 仅有介绍，本地未提供完整题目，不能给出考试覆盖率。
- 比较对象是本地课程快照和固定代码，不以课程示例代表当前 SDK 的最新 API。未联网验证最新框架版本。

| 文件编号 / 主题 | 本次对照依据 | HarnessAgent 的位置 |
|---|---|---|
| 00–03：目录、定位、直播 | 总体主题；不把直播效率宣传作为基准 | 控制面定位已明确，仍需完整业务纵切 |
| 04–06：CodeAct、自定义工具/MCP、多 Agent | 文件 04 第 9–11 页；05 第 4、7–9 页；06 第 2–4 页 | 固定 CSV 产品链路 + Scripted CodeAgent 沙箱探针；非真实模型驱动的 CodeAct 产品 |
| 07–10：Claude Loop、Skills、投研 SubAgent | 文件 08 的 Loop、两份 09 的 Skill、10 的分工章节 | Native SDK/MCP/SubAgent 代码存在；默认未准入；演示仍为模拟 |
| 11：Session / Fork | PDF 第 1、3、5 页 | 聊天历史和 metadata Handoff 存在；SDK resume/fork 产品链路未实现 |
| 12：Hooks | PDF 第 2、6–7 页 | 有各适配器权限拦截和事件映射；无统一的跨会话模式 Hook 治理闭环 |
| 13：OTel / 成本 | PDF 第 2、9–10 页 | 有持久 Event / 部分 SDK usage；无已接通的 OTLP 全链路和统一费用账 |
| 14：Deepagents / 旧项目升级 | PDF 第 3–6 页 | 设计映射与可选框架路线，不是已接入的 Deepagents Backend/Middleware |
| 15–16：LLM-Wiki | 文件 15 第 3–5 页；16 第 2–3 页 | Source/Fact/Graph 已有；Wiki 编译、index/log 自动维护仍 Proposed |
| 17–18：Pi Runtime、工具、结构化输出 | 文件 17 第 2–4 页及文件 18 解析/输出章节 | Pi core 真实循环 + Faux Provider；本平台不是完整业务审查 SDK |
| 19–20：长合同 Skill、拦截管道 | 文件 19 第 2–5 页；20 第 2–4 页及流程图 | 本地切分/敏感检查、沙箱边界已有；真实语义流水线主要在独立仓库 |
| 21–22：Web / TUI | Web/TUI 组件与事件章节 | 本平台已有 Web/SSE；独立仓库已有业务 Web/TUI；不要求照搬组件库 |
| 23：DeepSeek Harness 加餐 | 插件、Profile、生命周期与课程预览定位 | 可选研究项，不应为凑齐框架数量而接入 |
| 24–25：结语、测试介绍 | 非实现规格 | 不计功能缺口；没有完整考试题，不评分 |

## 2. 主要缺口（包含已有基础和验收方法）

### G1 / P0：缺一条统一、可交付的真实 Agent 工具闭环

证据：

- `backend/provider_adapters.py:129` 构造的是纯文本 Chat Completions 请求；`:193` 明确拒绝 `tool_calls/function_call`。`docs/harness/AGENT_RUNTIME.md` 明确声明零 Tool/MCP/Skill 绑定，与 Product Task/Run 分离。
- `adapters/local.py:8` 的 LocalAnalyticsAdapter 是固定 `analyze()`；`actions.code=false`。`backend/service.py:72` 注册固定分析器，不是任意 CodeAgent 执行入口。
- `adapters/smolagents_probe.py:52` 使用 ScriptedProbeModel，证明引擎/执行器契约，不证明真实模型能写分析代码并迭代纠错。
- `pi-adapter/src/sidecar.mjs:29` 只允许 Faux 模型；`:55` 预置工具调用与结果。真实 pi-agent-core 确实参与循环，但模型输出是预定的。
- `docs/harness/EXTERNAL_SKILL_RUNTIME.md:70` 明确排除 Product Task/Run、模型和 MCP 自动接入；沙箱不是缺失，而是独立边界尚未与业务 Loop 连接。

缺口：把用户目标 → 固定模型/版本 → 有权限的工具执行 → observation 回流 → Artifact/Handoff → Gate → 终态，绑定在一个可取消、可核对预算的 Product Run 上。

验收建议：一个已授权 Public 输入，从前端实际发起；至少发生一次模型工具调用及结果回流；产物引用源版本；拒绝/取消/超时后不再执行工具、不发布成功；重放不新增调用；关门时拒绝而不是退回假结果。合成测试和真实 Provider 冒烟分开交证据。

### G2 / P0：真实投研是“已接代码、未准入验收”，不是没写

证据：`adapters/claude_research.py:210` 定义三个角色，`:231` 构造来源 MCP Server，`:280` 构造真实 SDK options；`backend/research_native.py` 已映射到 Product Run。对照 `docs/harness/CLAUDE_RESEARCH_RUNTIME.md:35,60,66`，仍缺本次批准的模型/资料源/预算/责任人及真实 SDK-MCP、SubAgent 并发/取消/费用证据。`backend/research_agents.py:1` 则明确是零模型零网络模拟。

下一步不是重写三角色，而是准备完整准入包后跑有界集成验收。课程的外部搜索/金融 API 不是现成授权；不能拿模拟结果代替真实来源。不要和 G1 同时大规模铺开，先选择一条业务纵切。

### G3 / P1：Session 历史、业务 Checkpoint 不等于 SDK Resume / Fork

课程文件 11 展示在同一历史上继续，以及派生互不污染的分析分支。

当前：`backend/agent_runtime.py:274` 组装最近若干轮消息；`backend/team_session_continuity.py:47,65` 是 metadata-only 交接，不保存/压缩/恢复 Provider 上下文。Claude options 未配置 resume/fork；固定 CSV checkpoint 只覆盖确定性边界。

缺口：SDK session ID 与 Run/版本/权限快照绑定、重启后受控续聊、fork 的父分支关系、分支预算与产物隔离。独立 Pi 项目 `src/session.ts:74` 也明确使用 `SessionManager.inMemory`，SQLite 报告历史不能算完整模型会话恢复。

验收建议：进程重启后续接；从同一检查点 fork 两条不同分析，原分支内容不变；新分支重查权限/预算，不能把历史凭证或工具授权无条件继承。

### G4 / P1：缺统一的 Hook / 工具治理桥接，不是完全没有护栏

已有：Claude `can_use_tool` 白名单、MCP 来源策略；Pi `beforeToolCall`；独立 Skill 沙箱；交付 Gate。课程文件 12 第 6–7 页强调 fresh/resume/fork 复用策略，文件 20 是多层工具拦截。

缺口：将工具调用前检查、参数摘要、逐项人工审批、结果脱敏、失败/取消、子 Agent 起止、会话收尾，统一关联 Run/Step/call_id；建立覆盖内部续轮与辅助模型调用的测试。`include_hook_events=True` 只是请求接收事件，不等于已经注册完整 Hook 管道。

Gate 是交付验收，不等于工具执行前审批；Hook 也不能代替 OS/容器沙箱。独立 Pi 项目已做不少这方面工作，应优先适配其行为与反例，而非复制课程里的正则黑名单充当隔离。

### G5 / P1：全链路遥测和统一费用账未落地

课程文件 13 强调主/子 Agent、模型、工具的嵌套 trace，以及 token/cost 聚合。

已有：SQLite Event、关联 ID、Source evidence；Claude `adapters/claude_research.py:343` 接收 `total_cost_usd/usage`。所以不能说“没有日志或任何费用信息”。

欠缺：在本次检查的 `backend/`、`adapters/`、`pi-adapter/src/` 与 requirements 中未找到 OTLP exporter/collector 接入和统一 tracer；聊天适配器收到 usage 帧后跳过（`provider_adapters.py:172`），不是费用账本。现有 Run 限额、SDK 上限与真实计费也不是同一个保证。

验收建议：一个 Run 的模型/工具/Child trace 可串联；按 Provider/模型/价格版本记录估算与实测用量、失败和重试；包括压缩/二次检查等辅助调用；缺 usage 时明确 unknown。若承诺费用硬上限，需调用前额度预留与可证明的最坏消耗约束，不能用事后统计冒充。遥测默认不导出 Prompt/合同正文/凭证。

### G6 / P1：LLM-Wiki 缺可执行编译器与维护闭环

课程文件 16 第 2–3 页的核心是 ingest/query/维护、跨页更新、来源引用、index/log，而不是仅导出 Markdown。

本平台 Memory Plane 已有显式 Source/Fact、时间过滤、FTS5、Entity/Relation、撤回/删除。`docs/harness/LLM_WIKI.md` 则明确 Proposed，W0–W3 未完成。独立项目的 KnowledgeRouter + Markdown 导出是会话知识归位，也不能直接算完整 Wiki。

验收建议：先做离线确定性 W1：同一 manifest 可重建页面/index/log；二次导入无重复；冲突更新保留双方来源；链接可校验；撤回/删除传播；Git diff 与 Gate 对应。模型抽取放到后续准入，不需要为了 Wiki 先引入 Deepagents。

### G7 / P1：检索组件已有，Agentic 检索控制器与业务效果证据不足

这是用户前面检索要求的补充对照，不把课程所有章节都解释成 Agentic RAG 要求。

已有：`backend/adaptive_retrieval.py` 的结构切分、父子文本/offset、Weighted RRF、父聚合、Slot 与六维预算停止函数；retrieval-state v1/v2 Schema 与 validator。相关 10 项定向测试包含在本轮 81 项里。

缺口：检索控制器调用真实受准入 retriever、逐轮写状态并核对预算、把证据交回业务 Agent。目前生产 backend 中这些 helper 的引用只在自身模块；`AGENTIC_RAG_ADAPTATION.md` 也明确控制器/缓存/自主路由未实现。不能把独立函数校验称为已上线 Agentic RAG。

本轮重跑 `harness/adaptive_chunk_evaluation.py`：2 个调参 + 2 个合成留出；留出 fixed Recall@1=0，adaptive=1，父扩展指标=1。数字可复现，但排序使用标注词的子串命中，留出 adaptive 各只有 1 个子块；这是切分边界演示，不是独立自然语言查询集，更不能证明泛化提升。

验收建议：固定 Query/文档/相关性标注，调参和留出隔离；加入多父块、表格、跨条款、矛盾和无答案；比较固定/结构切分、单路/融合、无/有父聚合；报告 Recall@K、证据覆盖/重复、首个有用结果时间、端到端延迟和预算。语义/API 路由和缓存仍保持既有禁用边界。

### G8 / P1：独立合同 Agent 到平台的复用边界尚未打通

独立仓库 `/Users/weberzhao/code/ai/pi-contract-review` 在 `21f9451`：

- `package.json` 引入 pi-coding-agent、pi-tui；`src/session.ts` 使用真实 AgentSession 与限定 Skill 发现。
- `src/review/pipeline.ts` 有分块、结构化 submit_risks、解析重试、受控手动压缩和全局复盘。
- `src/guard/approval.ts`、`src/extensions/security-guard.ts`、`src/review/budget.ts` 有工具审批和统一 token 使用账；`src/knowledge/*` 有确认后知识归位/注入。
- `src/web/`、`src/tui/` 是业务界面，`src/store/review-store.ts` 保存结构化结果。JWT 与用户隔离属于该仓库，不代表本平台已有身份系统，也不构成本次增设认证的授权。

以上是本次源码抽查，未重跑独立项目全量测试、模型调用或服务健康。其 `IMPLEMENTATION_NOTES.md:182–202` 记录已审代码、后续真实模型证据缺失及预算保证范围，不能把历史样本 16/16 外推为全量生产质量，也不据此断言现在额度仍然耗尽。

推荐集成时把其结果转换为平台 Artifact/Handoff/Gate，而不是第二套状态各说各话；特别保留风险引用校验、取消、预算和知识确认边界。本平台目前的 Faux sidecar 不应被称为这个完整 Agent 的部署版。

### G9 / P2：课程能力清单与当前状态文档需要同步

`docs/research/PI_CONTRACT_COURSE_17_22.md:31` 将 Pi Node sidecar 列为本切片不实现的内容，属于早期切片描述，不能再作为整个仓库当前状态；`FRAMEWORK_INTEGRATION.md:68` 与实际 sidecar 已说明后续实现。

建议每项能力维护“设计/离线组件/产品接入/真实验收/部署”五列和固定版本证据；功能测试数、API Schema 完整度、开发过程 review 通过，不是课程业务交付覆盖率。不要给出无依据的“课程完成 90%”。

## 3. 不应列为必须补齐的项目

- 不必同时引入 Smolagents、Claude SDK、Deepagents、Pi、DeepSeek。课程展示的是不同选型，不是生产系统必须运行五个框架。
- 不使用 pi-coding-agent/pi-tui 作为本平台服务端依赖本身不是缺陷；关键是是否具备所需行为。Web 不用 ChatPanel 组件也不是功能缺口。
- 语义检索、联网、缓存默认关闭是明确边界；只能登记待准入，不能为了“课程对齐”打开。
- 本平台维持 metadata-only 身份控制面是用户决定；另一个项目的 JWT 不自动迁移过来。
- 课程的简化命令过滤、Host 文件系统 Backend、自动写记忆不能原样当作生产安全方案。课程文字和示例 API 本身仍需按实际选定 SDK 版本核验。

## 4. 推荐顺序与最小交付

1. **先确认一个业务纵切**。按仓库现有 P0，完成真实 CodeAct 表格分析；若用户希望最快复用团队现有业务成果，可改为先接独立 Pi 合同 Agent，但这是优先级调整建议，本报告没有擅改 P0。
2. **同一轮补执行必需的统一边界**：Tool/Skill 沙箱绑定、预算与取消、Artifact/Handoff/Gate。只开完成该场景所需的最小工具集，不先做全能市场或全部框架。
3. **之后做 Session 恢复/Fork 与可观测性**，围绕已工作的场景验证，而非新增一批没有业务消费者的接口。
4. **再做 Wiki W1 和检索接入/评测**，先离线、来源可追踪，再申请模型化维护。

一个纵切的“完成”需分开报告：代码和离线回归、批准范围内真实 Provider、端到端业务质量、指定部署环境。任一层缺失就明确标为待办，不能互相替代。当前本报告没有验证 8765、132、3456 的在线状态或最新部署版本。

## 5. 本轮实际验证及非证据

在主仓库固定基线运行：

```sh
.venv/bin/python -m pytest -q tests/test_framework_catalog.py tests/test_provider_stream.py tests/test_adaptive_retrieval.py tests/test_retrieval_state.py tests/test_agentic_rag_state.py
# 81 passed, 1 warning in 1.96s
.venv/bin/python harness/adaptive_chunk_evaluation.py
# heldout: fixed=0.0, adaptive=1.0, parent_expansion_complete=1.0
```

81 是框架目录、协议、检索函数/状态的定向测试总数，不是业务验收率。测试使用已有离线夹具，没有请求真实 Provider，没有运行真实容器或发布，没有扫描全部 1430 项，也没新做安全突变。本报告只新增研究文档，不改业务代码、准入档案、正式 DB、部署配置或现有任务状态。

## 6. 交给 Reviewer 的具体问题

1. G1–G8 有没有把独立仓库能力算到主仓库，或把默认关闭误写为未实现？
2. Session/Fork、Hooks、OTel 和 Wiki 的缺口判断，是否有本报告漏掉的真实调用入口？请给文件行号反证。
3. 是否同意评测只能证明切分边界示例、不能证明真实检索泛化？检查脚本而非只看汇总数字。
4. 下一轮建议是否仍守住 metadata-only、默认禁用、一个业务纵切与独立 Gate 的边界？

完成标准：对这份对照报告给出 Approved 或 Changes Requested，附证据与范围。该结论不是对真实 Provider、所有课程代码、在线部署或合同专业质量的批准。
