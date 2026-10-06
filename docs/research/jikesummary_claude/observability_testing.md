# 子任务摘要：observability_testing

> 原样保存自会话 7b211228 中只读子任务的返回文本（未经编辑）。课程原文不入库。

The output file was not written. The harness refused the `Write` call ("Subagents should return findings as text, not write report files"), so `summary_observability_testing.md` does not exist. I didn't work around the block through the shell. The full content is below; the parent agent can save it to `/private/tmp/claude-501/-Users-weberzhao/7b211228-959f-4b10-a762-b0711e85c301/scratchpad/jike/summary_observability_testing.md`.

**5-line summary**
1. I read all 14 lectures in full (可观测性 6 讲, 测试质量 8 讲) and checked every claim against harnessagent-dsh @5939e5d. File:line citations are in the table.
2. Already strong in the project: the token ledger reserves before each call and freezes when usage is unknown; progress is judged by new evidence; events are metadata-only, with negative tests; review results are bound to a submission version and decided by a deterministic check; scripted fake-provider tests and mutation tests exist.
3. Main gaps: the payment eval is not in `verify.sh` and has no baseline or dataset hash; model and tool events record no `latency_ms`; there is no per-turn trace view; there are no trajectory assertions; prompt, tool and validator versions are not recorded.
4. Top 5 (P0, P0, P1, P1, P1): make the eval a baseline gate with a dataset hash; add per-call latency and failure fields; add a read-only `/runs/{id}/trace` view; add `trajectory_check`; stamp prompt and validator versions and write a risk-coverage table (implicit exceptions are detected 0/2).
5. Don't do: write contract text or `output_preview` into traces, or record replay tapes from real runs; add auto model downgrade, routing or retry; give an LLM reviewer approval power, or build the full monitoring stack and money ledger.

---

# 可观测性 / 测试质量 课程摘要与 HarnessAgent DSH 对照

- 输入：`jike/可观测性/` 6 讲、`jike/测试质量/` 8 讲，共 14 讲，全部通读。
- 被对照项目：`~/code/ai/harnessagent-dsh`，分支 `dsh/local-runtime-20261005`，HEAD `5939e5d`。下文 file:line 均指该提交。
- 注意：文件名前缀不等于讲次。测试质量目录里有两个“27讲”，分别属于两门不同的课。

## 一、逐讲摘要

### A1. 《Java Agent》13｜系统集成：Agent 能力与现有系统无缝对接（张嘉熙）
- **核心观点**
  - 在现有系统之上加一层很薄的 AI 适配层，实体、Repository、Service 和事务都不改。
  - 把 Service 工具化时要写清四个要素：名称、描述（含输入 JSON 字段含义）、执行逻辑（try-catch 兜底）、统一的文本返回值。空结果和异常也要返回明确提示。
  - 有状态实体用 EntityView 模式：LLM 思考时不占数据库连接，调用工具时才开毫秒级短事务重新加载实体。这样能避开事务超时和 `LazyInitializationException`。
  - 工具提供可选的过滤参数，让模型按需取数，省 Token 也更准。
  - RAG 复用已有 DataSource。
- **排雷方法**：不要把“活实体”传进工具，否则事务超时和懒加载失效两类故障会同时出现。
- **原文**：“调用 LLM 时不持有数据库连接，LLM 调用工具时才开启毫秒级短事务重新加载实体。”

### A2. 《生产级 Agent 排雷实战》15｜网格化天眼账本（李号双）
- **核心观点**
  - 成本 = 用户量 × 单次成本 × 失控系数，失控系数在 1 到 50 之间。来源有三：推理路径、子任务膨胀、上下文膨胀。
  - 度量层看单位任务成本，账本要细到 Run、Step、Sub-Agent。子 Agent 的开销折叠回父 Run，并按多个维度归因。
  - 设四轴硬熔断：轮数、时间、Token、金额。每轮前后都查账，超了就抛 `BudgetExceeded`，按层级阻断。
  - 动态预算按里程碑发放，用进度换预算。最近 5 轮没有新调用或新信息就拒绝追加；追加超过 2 倍要人工审批。
  - 预算用到 80% 时自动降级，并做模型路由与渐进式升级。
  - 防御层：动态时间戳会粉碎前缀缓存。只追加的内容放前面，每轮重写的内容放最后，并监控缓存命中率。
- **排雷方法**：单位成本达到均值的 5 倍，多半是死循环或 Prompt 退化；达到 10 倍时要触发安全评估。命中率骤降，说明有人改了 Prompt 结构。
- **原文**：“轮数防死循环，时间防挂死，都是钱的粗糙代理；只有金额轴直接对应账单。”

### A3. 《生产级 Agent 排雷实战》16｜Agent 全链路监控体系（李号双）
- **核心观点**
  - Agent 的故障多是“认知故障”：日志里全是 200，结果却做错了事。所以要加一个 Audit 维度。
  - 统一观测模型：Trace、Observation（Span 和 Generation）、Session、Score。Generation 记录 promptVersion、usage 和 cost；Score 是监控、测试、评估共用的“质量货币”。
  - Prompt 版本、CoT、召回内容这类意图字段要实时富集，不能事后补录。写入走异步，不阻塞业务。
  - 黄金轨迹放进 Dataset（期望工具序列、forbidden_tools、constraints、tags），用内容哈希锁定版本。在线 Evaluator 把 `trajectory_drift` Score 写回 Trace 并告警。
  - 宽表 + 不可变：Score 以新记录追加，不修改原 Observation。
- **排雷方法**：漂移有四种，即偷步、加戏、替换、乱序。前两种用集合差能抓到，后两种必须做有序比对，所以要同时记录 `name` 和 `startTime`。
- **原文**：“四种漂移中 set 运算只能抓偷步和加戏，替换和乱序必须靠有序比对。”

### A4. 《从 0 开始构建 Agent Harness》18｜在 Harness 层拦截 Token 与耗时（Tony Bai）
- **核心观点**
  - 在 Provider 适配层用装饰器 `CostTracker` 拦截，Main Loop 不改。
  - 透传 Usage 并累加到 Session。
  - 一个 Turn 的耗时 = 模型耗时 + 工具本地耗时。只拦截 Generate 会漏掉工具耗时，所以 Registry 上也要挂环绕中间件。
  - 调用失败时只记耗时、不计费；没有返回 Usage 时要显式告警，不能当作 0。
- **排雷方法**：看每轮输入 Token 的增长，判断上下文是否在累加。
- **原文**：“输入 Token 会随着对话轮数呈现出近似 O(n²) 的增长趋势。”

### A5. 《从 0 开始构建 Agent Harness》19｜引入 Tracing 复盘失败决策路径（Tony Bai）
- **核心观点**
  - Trace 是一棵树：Run → Turn → LLM.Thinking / LLM.Action / Tool.Execute / Compaction。
  - 用 `context.Context` 级联父子 Span。属性包括 `duration_ms`、`context_message_count`、`tool_name`、`arguments`、截断到 100 字的 `output_preview`、`intercepted/reject_reason`、`error`。
  - 结束时 defer 导出 JSON。并行工具的区间会重叠，可以画成甘特图。
  - 延伸方向：LLM 增强型 Trace；多 Agent 场景用 trace_id 加 parent_span_id 组成 DAG；运行时追踪要和认知追踪结合。
- **排雷方法**：
  - `context_message_count` 用来判断上下文是否爆了。
  - `arguments` 用来查幻觉参数。
  - 哪一层 `duration_ms` 最大，就从那里优化。
- **评论区纠错（作者已确认）**：在 for 循环里写 `defer span.End` 会导致耗时不准，还会泄漏内存；子 Agent 的 Trace 没有被收集。

### A6. 《Claude Code 企业级全链路》29｜可观测性与排错（Robert）
- **核心观点**
  - 一期必做：结构化 JSON 日志、依赖级健康检查、LLM 耗时与熔断指标、慢请求 WARN。
  - 一期不做：单体应用的分布式追踪、前端监控、ELK。
  - 要提前做的三个决定：Actuator 单独端口；现在就把 traceId 放进 MDC；尽早定好日志字段规范（sessionId、agentId、providerId、modelName、action、durationMs、success、errorCode）。
  - MDC 跨线程会丢失，需要包一层 wrapper。
  - 依赖 DOWN 时健康检查返回 503，K8s 才会摘流量；未配置的依赖记为 skipped。
  - 告警分 P0/P1/P2，同时维护一份“不建议告警”清单，例如 HALF_OPEN 不告警。
- **排雷方法**：用 traceId 过滤，`durationMs=3768 providerId=2` 两分钟就能定位到 Provider。DistributionSummary 不开 `publishPercentileHistogram` 就不会生成 `_bucket`，P95 面板会是空的。
- **原文**：“日志字段一旦进了生产，改名代价极高，所有grep和告警规则都要跟着改。”

### B1. 《Java Agent》12｜单元、集成、E2E 三层测试（张嘉熙）
- **核心观点**
  - 用替身代替 LLM，但 Prompt、温度、工具组、调用次数都要验证。
  - 单元测试用 Fake 记录每次 LLM 调用，断言内容并断言恰好调用 1 次。
  - 集成测试用 `verifyNoMoreInteractions()` 防止出现意外的额外调用。
  - E2E 只跑 1–2 条核心闭环，用宽松断言，不在每次 CI 中运行。三层比例为 6:3:1。
- **原文**：“E2E 测试只覆盖 1-2 个核心业务闭环，不在 CI 中每次运行，而是绑定到预发布流水线或手动触发。”

### B2. 《老项目改造实战》14｜摸清现有测试（Robert）
- **核心观点**
  - 目标是关键路径有兜底，不是追覆盖率。
  - 四步法：
    1. 找核心链路，不超过 8 条，起点和终点都能写成断言。
    2. 按链路统计测试，而不是按文件统计。
    3. 实际跑一遍，并给失败分类：代码 bug、测试坏了、环境问题。
    4. 列缺口清单，不超过 20 项（P0 5–10 项，P1 不超过 10 项）。
  - 健康度要把“跳过”和“失败”合起来算：绿 ≥90%，黄 60–90%，红 &lt;60%。
  - 约束 AI 的三条：给数量上限；不在主链路上的不列；强制分出 P0/P1。
- **排雷方法**：AI 容易把“有测试文件”当成“链路已覆盖”，也容易把失败都归为环境问题。
- **原文**：“每个 P0 都要能直接回答‘如果不补这个，AI 改了什么我会发现不了’。回答不了的不是 P0。”

### B3. 《老项目改造实战》15｜Characterization Test 锁住行为（Robert）
- **核心观点**
  - 锁住“现在实际做什么”：先跑代码，记录真实结果，再转成断言。
  - 优先级：Characterization &gt; 核心链路集成 &gt; 复杂逻辑单元测试 &gt; 简单 CRUD（可以不补）。
  - 每批 1–3 个，跑通、review 之后再开下一批，失败的测试不能带进下一批。
  - 必须进 CI，失败就阻断合并。
- **排雷方法**：遇到“应该等于 100”这类断言，要问清这个 100 是从哪来的。
- **原文**：“不要凭‘应该是什么’写断言，凭‘实际是什么’写。”

### B4. 《生产级 Agent 排雷实战》18｜日志全绿，事故照发：Agent 测试护栏（李号双）
- **核心观点**
  - 测试的定位是护栏（Fence），不是验证（Verify）：盯住有限的违规路径。
  - 第一层：用 FakeLLM 剧本主动制造失败路径，例如幻觉出 `delete_table` 或异常返回，验证会被拦住，且拦住后任务还能继续。
  - 第二层：Trace-to-Test。事故 Trace 一键入 Dataset，用 Replay 零网络回放。卡带用完就报 “Cassette exhausted”。Dataset 按内容哈希锁定版本，并打 tags。
  - 第三层：`TrajectoryAssert`，包括 called、then、never_called（一票否决）、no_repeated_calls、called_with。
  - CI 门禁分 PASS/WARN/FAIL。阻断类维度直接 FAIL；Evaluator 自身不稳定时只标记，不否决业务。
- **排雷方法**：只看结果关键词的断言，发现不了“过程违规、结果蒙对”。
- **原文**：“传统测试是 Verify……Agent 测试是 Fence，定义违规边界、保证它不越界。”

### B5. 《从 0 开始构建 Agent Harness》20｜Benchmark 自动化评估（Tony Bai）
- **核心观点**
  - 沿用 SWE-bench 的 Fail-to-Pass 思路：靶机 Setup，加客观的 ValidateScript，每个用例用隔离的工作区。
  - 结果要记录成本、耗时和轮数，并和基线比较决定是否回滚。
  - 结果评估与轨迹评估要区分：3 步完成和 20 步完成不一样。
  - 其他方向：LLM/Agent-as-Judge；子目标完成率；动态 Benchmark 防过拟合；接入 CI。
  - 评论区方案（作者认可）：增加 `toolFailureCount` 和 `recoveryCost`。
- **原文**：“一个 patch 被接受，当且仅当所有由失败转为通过的测试都翻转成功，且没有引入任何新的测试失败。”

### B6. 《AI 原生开发工作流》19｜AI 驱动的 TDD（Tony Bai）
- **核心观点**
  - 红：测试能编译但运行失败。绿：用最少的代码让它通过。重构：在测试保护下进行，并重跑。
  - 用 httptest Mock Server 隔离外部依赖；为了可测试性引入依赖注入。
  - TDD 用来防“自洽幻觉”：同一个 AI 写出错误代码，再配一个迎合错误的测试。
  - 意图偏差就改 spec，实现错误就直接修代码。
  - 评论区补充：
    - 禁止 AI 修改测试，例如在权限里 `deny Write(*_test.go)`，或先提交测试再看 diff。
    - 测试要写在行为或契约边界上。
    - 不适合 TDD 的场景，用一个只拿 spec 的独立 Agent 来出验收清单。
- **原文**：“在AI时代，代码生成成本极低，‘正确性’才是最稀缺的资源。”

### B7. 《Claude Code 企业级全链路》27｜质量靠体系（Robert）
- **核心观点**
  - 质量分四层：核心链路（由人判断）、单元、集成、混沌。
  - 架构、数据模型、安全边界、性能关键代码由人把关。
  - 双模型 review 时加一句“不需要夸代码写得好”。这样找出了越权、SQL 取到最旧消息、工具失败静默返回 mock 数据、读改写无锁等问题。
  - 写单测前先问三个问题：有没有 IO？去掉 IO 后逻辑还复杂吗？改动频繁或出错影响大吗？
  - 禁止在测试里重新计算期望值。
  - 已知 bug 先写红测试；越权的现状先用测试锁住，修好后测试“变红才是对的”。
- **原文**：“80-90% 的代码可以放心给AI写，前提是你知道剩下的10-20% 在哪里。”

### B8. 《Agent 设计模式之美》27｜生成评审（黄佳）
- **核心观点**
  - 评审结论绑定具体版本。修订稿状态为 UNREVIEWED，必须显式复审。
  - 三种权限（maker-checker）：生成者和修订器只能提案；评审者只能观察和举证；放行由确定性的策略闸 `AcceptancePolicy` 决定。
  - 证据闸：Issue 必须带 `check` 和 `evidence`；低分也要附 `score_evidence`。没有证据的意见放进 `dropped_issues` 留痕，并冻结为 tuple。
  - 有证据不等于覆盖了风险：需要一张风险覆盖表，并做“橡皮图章”消融实验。
  - 要同时具备事实独立和认知独立。ReviewReceipt 记录 digest、critic/policy 版本和证据快照。
  - 上线后看四个指标：错放率、误拦率、覆盖率、版本逃逸率。
- **排雷方法**：补偿性错误（加总对得上）只能逐条按主键比对才查得出。
- **原文**：“调用过评审者，不等于完成了有效评审。”

## 二、与项目对照表

| 课程要点 | 讲次 | 项目现状 | 建议优化（可实现、可测试） | 优先级 | 风险/不要做的理由 |
|---|---|---|---|---|---|
| 每次调用前后查账，超限即停 | A2 | **已做，且更严**：&lt;ul&gt;&lt;li&gt;先 reserve 检查余额 `business_budget.py:120-144`&lt;/li&gt;&lt;li&gt;mark_sent `154`&lt;/li&gt;&lt;li&gt;settle `174-201`&lt;/li&gt;&lt;li&gt;用量未知就冻结 `162-172,212-219`&lt;/li&gt;&lt;li&gt;不重试 `dsh_runtime.py:294-297`&lt;/li&gt;&lt;/ul&gt; | 保持 | — | 不要为了动态预算放弃按上限保守预留（`dsh_runtime.py:286-289`） |
| 子 Agent 成本折叠回父 Run | A2 | **已做（机制层）**：`bind_member` `business_budget.py:110-118`；按 root 汇总 `84-93` | 引入子 Agent 时，补一条测试：子 Agent 的消耗会计入 root | P2 | 现在没有子 Agent，不要提前造 |
| 四轴硬熔断 | A2 | **部分**：&lt;ul&gt;&lt;li&gt;模型调用 8 次 `dsh_runtime.py:31,253`&lt;/li&gt;&lt;li&gt;工具调用 32 次 `32,313`&lt;/li&gt;&lt;li&gt;截止时间 `201-205`&lt;/li&gt;&lt;li&gt;Token 账本&lt;/li&gt;&lt;li&gt;金额轴不适用（coding_plan 计费，`106`）&lt;/li&gt;&lt;/ul&gt; | 详情页统一展示各轴的用量和上限 | P2 | 硬编码价格换算出来的金额会误导 |
| 单位任务成本与异常检测 | A2 | **缺口**：每个 Run 有快照，前端显示在 `frontend/dsh.js:37`；没有跨 Run 聚合 | 只读汇总：按 template 统计 P50/P95，超过 P95×k 标红；用合成数据测试 | P2 | 单用户本地，不接告警 |
| 动态预算、80% 降级、模型路由 | A2 | **刻意不做**：`allow_fallback: False`（`dsh_runtime.py:111`）；不回退到联调模式（`84`） | 不做 | — | 会让评测结果不可比，也没有 HITL 审批人 |
| 按信息增益判定进展 | A2 思考题 | **已做**：只把新证据块算作进展 `dsh_runtime.py:337-354`；停止规则 `37-38,241-249` | 评测行加上 notices 和停止次数 | P2 | — |
| 前缀缓存：动态内容放在末尾 | A2 | **部分**：&lt;ul&gt;&lt;li&gt;状态消息在末尾 `dsh_context.py:166`&lt;/li&gt;&lt;li&gt;stub 会改写前缀&lt;/li&gt;&lt;li&gt;usage 丢失缓存字段 `dsh_provider.py:87-89`&lt;/li&gt;&lt;/ul&gt; | 如果 Provider 返回缓存命中数，透传为 `cached_input_tokens`（只记数字） | P2 | 不要为了命中缓存而取消 stub，stub 是 fail-closed 的保障 |
| 在 Provider 层拦截 Token 和耗时 | A4 | **部分**：&lt;ul&gt;&lt;li&gt;`dsh.model.completed` 只有 usage，没有耗时 `dsh_runtime.py:306-307`&lt;/li&gt;&lt;li&gt;`dsh.tool.completed` 没有耗时 `356-360`&lt;/li&gt;&lt;li&gt;只能拿 `occurred_at` 相减 `store.py:258`&lt;/li&gt;&lt;li&gt;probe 只记录整个 Run 的秒数 `dsh_real_payment_probe.py:58,70`&lt;/li&gt;&lt;/ul&gt; | 用 monotonic 时钟计算 `latency_ms`，写入两类事件，`run.failed` 也记失败 crossing 的种类和耗时；测试注入 sleep 后断言耗时值，并做正文反向断言 | **P0** | 只记数字 |
| Tracing 树 | A5、A3 | **部分**：&lt;ul&gt;&lt;li&gt;扁平事件，含 `trace_id/sequence/occurred_at`（`store.py:252-262`）&lt;/li&gt;&lt;li&gt;crossing 有 `model_round`（`dsh_crossings.py:64-69`）&lt;/li&gt;&lt;li&gt;context.assembled `dsh_runtime.py:264`&lt;/li&gt;&lt;li&gt;failed_step `479-481`&lt;/li&gt;&lt;/ul&gt; | 只读投影 `GET /runs/{id}/trace`，按 model_round 组成树，加前端折叠视图；用固定剧本断言树形和 `SYNTH_*` 反向断言 | P1 | 只做投影，不改写事件 |
| 记录 promptVersion，意图可溯源 | A3、A5 | **缺口**：只有 `estimator/state_sha256/messages_sha256`（`dsh_context.py:170-174`）；`release` 只出现在 `status()`（`dsh_runtime.py:57,69`） | `run.started` 和 findings record 加 `prompt_digest/tools_digest/validator_version/release`；测试：改 prompt 后 digest 变化 | P1 | 只记摘要（prompt 里拼了 objective） |
| Trace 只记元数据 | A5、A3 | **已做，且更严**：只记 `arguments_sha256`（`dsh_runtime.py:356-360`）；反向测试见 `tests/test_dsh_runtime.py:38`、`test_dsh_adversarial.py:196,287`、`test_dsh_payment_findings.py:203` | 新加字段同样配反向测试 | — | 见第三节“不该做”第 1 条 |
| 漂移检测：有序比对 | A3 | **部分**：dsh-plan@1 投影（`dsh_plan.py:29,62`；`dsh_runtime.py:214-227`），事件序号可以还原顺序 | 离线 `trajectory_check`：先读后引、发布前必须 accepted、策略拒绝后不能有对应的 tool.completed；评测行输出 `trajectory_ok` | P1 | 不做在线 Evaluator 和告警 |
| 尽早定日志字段规范 | A6 | **部分**：envelope 统一（`store.py:256-259`），`data` 里的字段没有规范 | 新字段写进 `specs/v1/dsh-runtime.schema.json` 并加校验测试 | P2 | 不要大规模重命名已有字段 |
| 健康检查与分级告警 | A6 | **部分 / 不适用**：`status()` 见 `dsh_runtime.py:67-77` | 不做告警 | P2 | 不搭 Prometheus/Grafana |
| FakeLLM 剧本与失败路径 | B4、B1 | **已做**：&lt;ul&gt;&lt;li&gt;不看标签的剧本 provider `dsh_payment_eval.py:25-70`&lt;/li&gt;&lt;li&gt;不可信结果不发布 `tests/test_dsh_runtime.py:192`&lt;/li&gt;&lt;li&gt;工具策略 `test_dsh_adversarial.py:334`&lt;/li&gt;&lt;li&gt;调用上限 `71,91`&lt;/li&gt;&lt;li&gt;非法 usage `115`&lt;/li&gt;&lt;/ul&gt; | 保持 | — | — |
| verifyNoMoreInteractions | B1 | **部分**：上限类测试断言了精确次数 | 成功路径的测试统一断言 `budget.calls` | P2 | — |
| Trace-to-Test 与卡带过期 | B4 | **缺口，且受约束**：crossing 回放只在单个 Run 内有效（`dsh_crossings.py:1`）；事件里只存哈希 | 只对合成公开合同做 opt-in 卡带，放在 `harness/eval/cassettes/`；`ReplayProvider` 用完时抛 `CASSETTE_EXHAUSTED` 并让测试失败 | P2 | 绝不从真实 Run 录制 |
| Dataset 内容哈希 | B4、A3 | **缺口**：报告里没有哈希（`dsh_payment_eval.py:153-156`）；labels 在 Run 之后才读（`151`），这点已做 | 报告加 `dataset_sha256`；与基线比较时哈希不一致直接报错 | **P0** | — |
| Benchmark 接入门禁并对比基线 | B5、B4 | **缺口**：`harness/verify.sh:1-30` 不跑评测，tests 也不调用；HA-0081 有 eval.json（21 例），HA-0082/0083 的证据目录里没有 | `--baseline HA-0081/eval.json --check`，指标下降或 calls 明显上升时退出码非零；用一个突变证明门禁会变红 | **P0** | 门禁只用合成 provider，不用真实模型 |
| 评测行记录成本、耗时、试错 | B5 | **部分**：rows 只有 `model_calls/coverage_warned/business_status`（`dsh_payment_eval.py:133-136`）；tokens 已取到但没写进行（`96`） | 增加 tokens、tool_calls、rejections、notices、elapsed_ms、trajectory_ok | P1 | — |
| 评审绑定版本 | B8 | **已做**：&lt;ul&gt;&lt;li&gt;`content_sha256` 加 superseded_by（`dsh_runtime.py:380-382`）&lt;/li&gt;&lt;li&gt;以最后一次提交是否通过为准（`376-378`）&lt;/li&gt;&lt;li&gt;由平台渲染，不发布模型自由文本（`454-457,465`）&lt;/li&gt;&lt;/ul&gt; | 保持 | — | — |
| 确定性放行 | B8 | **已做**：`verify` 见 `dsh_findings.py:134`；被拒超过 2 次即失败（`dsh_runtime.py:33,391-392`）；`human_review_required`（`452`） | 保持 | — | 不引入 LLM 拍板 |
| 无据意见留痕 | B8 | **已做（对应物）**：被拒的提交会写进 submissions 历史（`dsh_runtime.py:387,451`） | — | — | — |
| 风险覆盖表与消融实验 | B8 | **部分**：&lt;ul&gt;&lt;li&gt;语义未校验，已声明（`dsh_runtime.py:450`）&lt;/li&gt;&lt;li&gt;隐含例外 0/2（`harness/evidence/HA-0081/eval.json`）&lt;/li&gt;&lt;li&gt;突变测试在 `harness/evidence/HA-0083/mutations/`&lt;/li&gt;&lt;/ul&gt; | 补一张覆盖表；加消融测试：关掉候选词表后，lexical 指标必须下降 | P1 | 不要宣称语义已校验 |
| ReviewReceipt | B8 | **缺口**：只有 `schema_version` 和 `verification`（`dsh_runtime.py:445-450`） | record 加 `validator_version` 和 `release` | P2 | — |
| 不可变审计 | A3 | **已做**：只 INSERT（`store.py:260`）；与计划在同一事务（`dsh_runtime.py:206-213`） | — | — | — |
| Characterization 锁住行为 | B3 | **缺口**：`execute` 是约 300 行的闭包（`dsh_runtime.py:171-487`） | 重构前用 3 个固定剧本，锁住 `(event_type, data 键集合)` 的事件序列（golden，去掉 id 和时间） | P1（重构前做） | 只锁结构，否则过于脆弱 |
| 突变测试防假绿 | B6、B3 | **已做**：`harness/dsh_validation_mutations.py:1-5`，以及 HA-0083 的 7 个突变 | 新门禁也各配一个突变 | P1 | — |
| 已知 bug 先写红测试，静默失败要可见 | B7 | **已做**：`tests/test_dsh_runtime.py:95,266` | — | — | — |
| 混沌测试 | B7 | **部分**：SIGKILL 恢复 `tests/test_dsh_runtime.py:303`，重启 `163` | 按需补超时与取消的竞态 | P2 | — |
| 真实模型 E2E 不进 CI | B1 | **已做**：`dsh_real_payment_probe.py`（合成合同，HA-0081 有 rep1–3） | 保持 | — | — |
| 工具设计与短事务 | A1 | **已做**：分页 `dsh_runtime.py:325-335`；模型调用不在事务内（`301`）；每个事件一个短事务（`206-213`） | — | — | — |

## 三、结论

### 最值得做的 5 项
1. **（P0）把 payment eval 变成回归门禁。** 加 `dataset_sha256` 和 `--baseline --check`，接入 verify。再用一个突变证明门禁确实会变红。
2. **（P0）补上耗时和失败字段。** `dsh.model.completed`（`dsh_runtime.py:306`）和 `dsh.tool.completed`（`356`）加 `latency_ms`；`run.failed` 补上失败 crossing 的信息。只写数字，并配正文反向断言。
3. **（P1）做只读的决策路径投影 `/runs/{id}/trace`，加前端折叠视图。** 按 model_round 组织 Run → Turn → Model/Tool/Findings。
4. **（P1）实现 `trajectory_check`（then/never/accepted-before-publish/no_repeat）。** 评测行同时加上 tokens、tool_calls、rejections、notices、elapsed_ms。
5. **（P1）记录版本，补风险覆盖表。** 写入 `prompt_digest/tools_digest/validator_version/release`；覆盖表里把隐含例外（0/2）明确标为“靠人工”，并配一个消融测试。

### 诱人但不该做的 3 项
1. **把合同正文、参数原文、`output_preview` 或 CoT 写进事件/Trace，或从真实 Run 录制卡带。** 这些做法分别来自 A5、A3、B4，都违反“事件只记元数据”的契约。这条契约有测试锁定（`tests/test_dsh_runtime.py:38` 等），`dsh_context.py:28-30` 也明确禁止。
2. **自动降级、模型路由、动态追加预算、超时自动重试（A2 的做法）。** 这与 `allow_fallback: False`（`dsh_runtime.py:111`）、不回退（`84`）、用量未知时不重试（`294-297`）冲突，会让评测结果不可比，而且没有 HITL 审批人。
3. **让 LLM 评审器拥有放行权，或者搭建 Langfuse/ClickHouse/Grafana 全栈和金额账本。** B8 要求评审者只能举证，项目已经用确定性校验加人工复核来放行。本地单用户环境不需要那套重型栈；在 coding plan 计费下，用硬编码价格换算出来的金额是错的。
