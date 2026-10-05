# HarnessAgent 可吸收能力与分阶段接入方案

日期：2026-10-05。面向业务 Runtime 的研究建议，待 mymacclaude review；不是实现交付或开启门禁的批准。

结论：保留 HarnessAgent 的 Task/Run、权限快照、预算、Evidence、Artifact 和 Gate 控制面。优先吸收 DSH 的执行管线、Pi 的可替换循环、Dify 的知识处理和结果校验、Claude SDK 的进程治理经验。第一步不是再加一种引擎，而是把已有预算、护栏和沙箱接到真实调用边界，完成一个可验证的合同审查纵切；之后再复用到投研。

## 基线与证据范围

| 对象 | 固定基线与本地位置 | 本文使用范围 |
|---|---|---|
| HarnessAgent | `01908c91dd20664e11bc9cd5976b756bf8427eea`；`/Users/weberzhao/code/ai/harnessagent` | 当前代码、契约、任务状态；不是线上版本证明 |
| DeepSeek Harness | `5badb15009ae1756c3afe0ae0cef1faafc290ccc`；`/Users/weberzhao/code/oss/deepseek-harness` | 工具、循环、Session、沙箱、配置与 SDK 源码 |
| Pi | `f07218c4d4bbc12bef056a7058c3dd49dfe41abe`；`/Users/weberzhao/code/oss/pi` | v0.87.1 的分层与钩子语义，不泛化为所有实验模块 |
| Dify | `3be01cbb7adae1ac34eece12e246c037962152ed`；`/Users/weberzhao/code/oss/dify` | 稀疏克隆中 RAG、Agent 与工作流源码，未部署 |
| Claude Agent SDK | HarnessAgent `.venv/lib/python3.14/site-packages/claude_agent_sdk`，0.2.152 | Python 包装层；CLI 内部不是可逐行审查的开源循环 |
| 沟通材料 | pi-contract-review 的 `docs/HARNESSAGENT_ABSORB_FROM_CLAUDE_SDK.md`，修订 `45e5e503d253f11a901804d3cb91caad38dacd7a` | 综合其环境、隐私、结构化输出、目录清理建议；本项目未因此获得这些能力 |

“源码”表示能定位代码，不代表运行通过；“离线”仅指合成输入或临时库；“真实”必须有实际 Provider/CLI 行为；“部署”必须绑定发布身份和环境。本文主要是源码与设计证据。本轮重跑了旧的自适应切块评测脚本，结果与局限见第 7 项；没有运行 SDK/CLI、真实模型、容器或服务，没有接触 8765、132、生产 DB、Keychain。

基线已存在 `business_budget.py`（HA-0075），但实际业务发送链未接它。HA-0048/0049 是检索状态契约，HA-0050 有切块/排序/停止函数，不等于完整在线 Agentic RAG。某项代码获准、测试通过也不等于当前部署已启用。

## 先分清当前的四类运行对象

| 对象 | 现状 | 吸收时保持的边界 |
|---|---|---|
| Product Task 与 Run | CSV、Pi Faux、投研等显式引擎路径；事务化事件、产物、终态和 Gate | 唯一业务真相源；Adapter 不直接改数据库和业务终态 |
| Agent Runtime 聊天 | 独立 Session/Exchange；文本流与持久成功消息分开 | 不冒充 Product Run；断线取消后回读终态，不假装续传模型生成 |
| Agent Lab | 零模型演示 | 不把演示回复或静态状态当真实模型证据 |
| Team 控制面 | Workspace/Channel、Handoff、Attention、Team Session 元数据 | protocol actor 不是 HTTP 身份；不能拿来宣称多租户隔离或 Provider 会话恢复 |

依据：`backend/agent_runtime.py`、`backend/pi_contract_review.py:115`、`backend/research_native.py:231`、`docs/harness/LOCAL_WORKBENCH.md`。后者包含历史阶段描述，现状判断以固定代码和对应 ADR 为准。

## 优先级总览

以下是建议，不是已实现清单。“补齐”复用本地组件，“借鉴”独立实现设计，“复用”限于版本锁定的依赖接口。

| 项 | 吸收内容 | 方式 | 当前差距 | 优先级 |
|---|---|---|---|---|
| 1 | 干净的子进程环境及可归属的工作目录 | 借鉴与补齐 | CLI/sidecar 继承环境，cwd 与清理未按 Run 隔离 | P0 |
| 2 | 所有实际模型发送经过同一本预算账 | 补齐 | 有持久账本，没有业务 transport 集成 | P0 |
| 3 | 工具准备、审批、最终硬规则、隔离执行 | 借鉴与补齐 | 独立护栏 API 和容器尚未接成业务 Loop 执行链 | P0 |
| 4 | 内存内容与持久事件分离，候选结果独立验收 | 补齐，有限复用输出接口 | 存在正文进事件、主控结果未独立结构化等缺口 | 隐私 P0，输出 P1 |
| 5 | 请求上下文投影与受控压缩 | 借鉴 | 有 Memory/Retrieval 组件，无业务模型上下文控制闭环 | P1 |
| 6 | 版本化 Skill 与受控 Child Run | 补齐 | 有三角色与 Skill 快照，不是通用动态委派 | P1 |
| 7 | 父子文档检索的非平凡评测与迭代控制器 | 补齐 | 组件已实现，效果证据不足，控制器未落地 | P1 |
| 8 | 持久事件续读与分层观测 | 补齐 | Product JSON 游标已有，SSE/OTLP 不可混为聊天续传 | P1/P2 |

## 1 子进程边界与目录归属

**问题与证据。** `adapters/pi_sidecar.py:44–47` 的 Popen 没传 env/cwd。`adapters/claude_research.py:298–301` 使用仓库 ROOT 和少量 env 覆盖；SDK `subprocess_cli.py:809–839` 仍继承父环境，再添加 SDK 与可能的 OTel 字段。设 `options.env` 不等于白名单。独立 cwd 也不是 OS 沙箱。

**吸收。** 借鉴 DSH 能显式传子进程环境的启动接口，而不照搬其默认继承或遥测配置；Claude 路径优先使用显式 env 启动的受控 worker，避免并发请求中清空全局 os.environ。Pi sidecar 同样收紧。运行所需的 PATH/HOME/语言/TMPDIR 和 SDK 显式添加项逐一登记，模型认证沿用当前 CLI 自管登录，不擅自导出凭据。NODE_OPTIONS、NODE_PATH、LD_PRELOAD、DYLD_* 等不进入子进程。

**接入与契约。** Adapter 启动边界增加受版本约束的执行环境快照和 Run 所有权登记；只存变量名/配置摘要，不能哈希整份秘密环境充当公开快照。关 auto memory 的配置需要实测 CLI 行为，不能只靠环境单测宣布成功。改变 CLAUDE_CONFIG_DIR 可能影响登录，属于待验证推断和另行认证决策，不在本方案自动执行。

平台只清理登记的自有 cwd，先确认 worker 与子进程退出。跨 Run 路径、符号链接、归属或退出不明时保留并标记待清理。共享 CLI 会话目录暂不自动清理；将来需验证真实落盘布局、建立 Run/worker/session/精确文件映射，不能仅凭 session_id 拼路径或扫描共享 HOME。

**收益与代价。** 减少凭据继承、启动注入和会话污染；代价是 worker 协议、故障回收、CLI 认证兼容性。不是增加新 Docker 后端。

**最小验收。** 假 CLI 和真实子进程启动探针中放合成秘密与 NODE_OPTIONS 写文件哨兵；秘密不可继承，哨兵不能执行。成功/失败/取消/重启验证目录归属与清理；取消后仍写文件、跨 Run、符号链接、缺 session_id 必须安全保留或拒绝。实际 CLI 的自动记忆、配置查找和登录边界另列真实证据。

## 2 把预算接到实际发送位置

**现状。** `backend/business_budget.py:46,120,154,174,228` 已有 root/child 共用的 reserve→mark_sent→settle、取消、未知用量冻结；函数明确要求调用方提供可靠输入上界，并让 transport 限制输出且禁用隐藏重试。`service.py`、Pi 与 native 业务路径尚无该账本调用方。两千万 Token 是既定每根业务 Run 上限配置的能力，不是每轮都可花两千万，更不是要求花满。

**上游启发。** DSH `agent.ts:406–425,494–509` 重试会重新 prepareRequest/buildRequest，不重复 pre-step；只在 pre-step 检查会漏重试，`agent/request` 则覆盖这条重试路径。其 `llm-retry` 的 always 模式没有次数上限。Pi coding-agent 的 `before_provider_request` 异常会被 runner 吞掉，不能拿抛错当硬预算闸。这些都说明应控制最终发送，而非依赖观察事件。

**建议接入。** 第一条真实业务路径选择 Pi 合同审查的显式模型请求桥：sidecar 负责循环，平台受控 transport 持有实际发送权，调用 `budgeted_model_call`。这是新增协议设计，不是现有 `pi-adapter@1` 已支持。不要把 Key 发进模型 Prompt 或通用 sidecar 环境。冻结最终请求后计数、预留，再发送；任何改写必须发生在计数前，否则重新计数绑定。primary/child/retry/compaction/guard 各有 call_id/purpose，同属 root。

Claude CLI 内部发送不可假定能逐次拦截；当前 `max_budget_usd`、max_turns、外层 timeout 是另一条限额路径，不能伪称已接入 HA-0075。若无法覆盖其内部请求，继续保留独立准入限制，不授予同等硬 Token 上限保证。

**契约和代价。** 扩展 Adapter 模型请求/结果协议，绑定 Run、模型、权限与预算摘要；使用公开错误码区分未发送、已发送但用量未知、超额。取消或未知用量不自动释放已发请求预留，不切 Provider 重试。根 Run 的总截止时间、turn/工具次数和货币限额须在集成时分别强制执行，不能用单次调用 timeout 或 Token 余额替代。代价是 Node/Python 桥、供应商用量口径、辅助调用审计；输入计数若无法给可信上界，停在离线阶段。

**最小验收。** 合成 transport 对普通、重试、压缩、护栏二次模型、Child 各断言发送计数和预留一致；争抢最后余额最多一方获准。丢 usage、超输出、取消与发送竞态、迟到结果、重启均不能偷偷发第二次或发布成功。真实小额 Probe 另行批准，不能把账本测试作为供应商账单硬上限证明。

## 3 工具执行管线接入现有护栏和沙箱

**现状。** `backend/service.py:95,99` 分别实例化 PiSecurityGuard 与 ExternalSkillRuntime；`pi_security_guard.py` 只计算决策，无执行权。Faux `pi-adapter/src/sidecar.mjs:76–80` 只准一个固定 evidence_locate 组合，不是通用规则管道。`external_skill_sandbox.py:33–44` 已有禁网、非 root、只读文件系统、cap-drop 和资源限制，不能再说“没有沙箱”，但没有成为 Product Loop 的通用工具执行入口。

**上游启发。** DSH `packages/core/tools/src/index.ts:1493–1535` 先 pre-execute/approval，再单调 deny guard，随后经过 tools/execute 包装层调用工具 body。guard 不可被后续 allow 反转；结果观察者不是拦截器。其 sandbox 文件效果契约明确不包含网络隔离，不能替换本项目更严格的禁网容器策略。

**建议链路。**

```text
Product Run 的已冻结权限与资源快照
  → 参数 Schema 和硬拒绝预检
  → 需要时等待人工工具审批
  → 重查 Run/权限/参数摘要与最终硬规则
  → 已准入的只读资源工具或现有隔离执行器
  → 结果大小/结构/敏感信息检查
  → 给 Loop 的受控结果 + metadata-only 事件
```

这不是将业务最终交付 Gate 直接改造成工具审批。应在实现 ADR 中区分审批种类和状态，复用平台事务/幂等约束；工具审批绑定 run_id、call_id、工具版本、规范化参数摘要、权限摘要及有效期。审批期间参数改写、权限撤销、Run 取消、超时，均需拒绝；审批不是永久执行许可。待 HTTP 身份体系建立前，不把本地 human Gate 描述为安全的多租户审批。

**接入位置。** `pi_sidecar.py` 与 sidecar 工具回调只发请求，不直接执行；平台 service 调用 guard 与资源/隔离执行器。若以后改用 Pi coding-agent，高层会覆盖底层 before/afterToolCall，必须用正确扩展接口并测覆盖行为；当前轻量 core 不需要为了这个功能升级整层。

**收益与代价。** 一个执行入口统一审批、审计与取消；代价是往返协议、审批恢复、工具超时/副作用分类。工具实现不准另开不受控网络、进程或密钥路径。

**最小验收。** approve 后仍命中 hard deny 时执行次数为 0；审批摘要被改、重放、过期和取消皆为 0。护栏抛错不执行，观察回调不能授权。隔离工具出网失败、读未绑定资源失败、超时进程被回收；迟到结果不覆盖终态。先用合成工具证明管线，真实容器边界单列验收。

## 4 内容通道与候选结果验收

**现状。** `adapters/claude_research.py:324–344` 可产生 text/errors 等正文；`research_native.py:193–229` 将 payload 写入事件同时收集 Child 文本。Pi emit 在 `pi_contract_review.py:126–130` 整体写 payload。原生投研 `_aggregate:283–298` 检查三个 Child 的引用，主控文本不参与聚合；不能简单说换主控 output_format 就替代原正则。

**吸收。** 借鉴 Dify `agent_factory.py:27–47` 的 output_type 和 Pi/Claude 的结构化结果接口，但保持平台业务校验独立。原始内容走内存结果通道，持久事件单独投影：固定 kind/status/数量、摘要、受控引用；无正文预览、无任意 errors/stderr。只有批准的 Artifact 路径保存业务正文，不能把正文存成“摘要”规避边界。

主控结构化结果作为独立通道新增，不删除 Child 来源检查。要求角色全集、对应 Child 引用、缺口和冲突字段；Pi 候选必须绑定资源哈希、页码/文本偏移与证据。循环 idle、agent_end、finish_reason、合法 JSON 都不等于 run.succeeded，仍经平台验证和所需人工 Gate。

**契约。** SDK 传输对象和持久 event Schema 分开升级；保留老事件可读兼容。显式错误 subtype/is_error 拒绝发布。供应商 Schema 方言与平台 2020-12 契约分别处理，不把格式校验等同事实正确。引用存在只证明来源关系，不证明文本蕴含结论。

**验收与代价。** 文本、structured_output、errors、stderr 开头放合成秘密，events/诊断无命中，合法 Artifact 仍能交付；乱引用、错页、缺角色、未评估被改成肯定结论、取消后的候选全部拒绝。Schema 重试消耗预算且次数有界；语义质量用人工标注集单独验。代价是双通道与兼容迁移，收益是可验证输出和更小的数据泄漏面。

## 5 上下文投影而非复制完整会话日志

**上游与差距。** DSH 的 Session 日志/投影和 Pi SessionManager 展示了“持久事实”与“本轮模型输入”分离；DSH `agent.ts:669–678` 冻结请求消息。其 model-visible-means-logged 会存完整内容，本项目不能照搬。当前 Memory Plane 有来源、事实、生命周期和有界 Context，不是自动会话记忆，也没有接成每轮模型输入装配器。

**建议。** 在平台资源与 Memory 查询之上增加纯投影步骤：当前最小目标、准入证据引用、策略版本、近期必要结果 → 有界输入。请求摘要绑定投影版本和资源版本。上下文/Skill 更新不能在已计费预留后悄悄改变请求；更新应产生新快照。压缩器也必须经过第 2 项，压缩结果标为派生内容并保留来源关系，不能升级成用户指令。

**验收。** 同快照投影可复现；被撤回/删除证据不可再注入；插入“忽略规则”不改变权限；压缩失败可明确停止或按已定义无模型规则缩减，不能偷偷换 Provider。删除传播覆盖派生索引/上下文引用，但不虚称已有 WAL/备份/FTS 残留物理擦除。代价是 token 计数和 lineage；先不做自动长期记忆或跨租户缓存。

## 6 Skill 按需加载和有界委派

**来源与现状。** DSH 的 `docs/subsystems/skills.md`、`subagent` 能力族把技能发现、内容加载与代理后端分开。HarnessAgent 已有 `plugins/research-skills` 的三个第一方角色、Child Run 和工具缩权；`research_native.py:136–149` 记录固定子任务限制，不需要重建 Agent Team。

**建议。** 先给第一方 Skill 增加统一目录投影：名称、版本/digest、任务适用范围、所需能力，再按当前目标加载正文。Skill 是不可信任务资料而不是权限来源；不能自动执行其中 scripts，不能修改工具白名单。动态新增角色/外部 Skill 仍需显式选择和准入，不能因为 DSH 能热插拔就开放任意插件安装。

委派仍用 Product Child Run：子任务工具、资源、成本不超过根任务；取消向下传，结果向上以受控 Artifact 汇总。SDK 委派 ID 与平台 Child ID 明确映射；全局并发上限不能被嵌套代理绕开。不要把 DSH/Pi Session ID 或 Team actor 当作真实租户身份。

**验收。** 同名 Skill 漂移拒绝；无关 Skill 正文不进 Prompt；恶意 Skill 要求出网不执行；重复委派不多建 Child；Child 不能重开 root 预算；取消根任务后迟到 Child 不发布。收益是减少无关上下文并保持可替换性，代价是能力目录、映射与版本管理。

## 7 父子文档检索与评估闭环

**已有与相对不足。** `adaptive_retrieval.py:56,130,147,153,163` 已有结构切分、Weighted RRF、父聚合、上下文扩展、槽位与预算停止函数。Dify `ParentChildIndexProcessor:44` 则提供抽取/清洗/父子切分的系统性处理路径；可借鉴处理阶段及配置组织，不是照抄实现或默认开启向量库。

本轮运行 `.venv/bin/python harness/adaptive_chunk_evaluation.py`：两条留出样本的 adaptive_children 均为 1，fixed Recall@1=0、adaptive=1、父扩展完整率=1。脚本 `:19–21,29–35` 用标注 terms 的出现次数排序；在这两个样本上 adaptive 指标恒真。它支持切分边界示例，不支持“检索质量已优于基线”。不能拿这些数推动真实 RAG 准入。

**建议最小评测。** 第一版拟定 30 个独立 query，10 调参/20 留出，按源文档分组划分，至少覆盖跨窗口条款、表格、多级标题、冲突版本、无答案五类；每题候选不止一个，加入相似但错误的干扰条款。用户 query 与 gold evidence 分离，运行排序不可读取标注答案。数量是建议的启动规模，不是已完成测试集或生产统计保证。

比较固定长度/父子切分、单路/加权融合、无/有父聚合、单轮/固定迭代/按缺口动态策略。冻结语料、query、K=1/3/5、计算预算、参数与版本；不仅同 K，还给相同上下文字符/token 上限，避免父块无上限扩展作弊。检索只用已准入 keyword/temporal/graph 路由，semantic/api 继续关闭。

报告按 gold evidence ID 的 Recall@K、Precision@K、Claim 覆盖率、重复率、父上下文覆盖比例、首个通过 rubric 的有用结果耗时、总耗时和调用/token 成本。父块扩展按明确 gold span 计算，不写死 1；多个子块命中同一来源不能充当多份独立证据。测试集全部金标及无答案拒答 rubric 在调参前冻结。

**决策规则。** 安全/无损/预算反例必须全过；候选策略在留出集的宏平均证据覆盖率和 Recall@3 不低于固定基线，且满足预先约定的上下文/时间预算，才允许进入真实评测。样本小只能支持继续实验；动态策略应重复运行并报告不确定性，冷/热缓存分报，但身份体系缺失时缓存保持禁用。此规则是建议验收门槛，不是已测结论。

**接入与代价。** 先扩展 `harness/adaptive_chunk_evaluation.py` 和独立 fixture，再实现调用已有 retrieval-state@2 validator 的控制器：缺口驱动 query、合并去重、无进展只换一次、预算耗尽硬停。纯函数返回 stop 不是运行时停止证据，必须验证实际工具调用数不再增加。代价是标注、版本化语料与真实评测预算。

## 8 持久事件续读和可观测性

**现状与建议。** Product 已有 `store.py:264` 的事件序号游标。可新增只读 SSE，让 id 对应持久 sequence；重连只读库，不重启模型；无重复/遗漏及游标过期错误要按明确契约验证。Agent Runtime 的 delta 没有持久游标，保持断线取消与有限回读终态，不因为加一个 id 字段就声称支持续传。

观测先做本地 metadata 指标：call_id、step、purpose、队列/模型/工具/审批耗时、取消确认时刻、预算预留与实际用量。分别报告“首个合格结果”和“最终交付”，不能拿向量查询耗时替代端到端性能。以后才加默认关闭的 OTLP exporter，绑定准入和目的地。

**不能照搬的上游默认。** DSH base 的 Session telemetry 是 FEEDBACK_ONLY，但反馈可把含原文日志发到 DeepSeek collector，且与模型厂商无关；desktop 还独立启用产品分析（base patch:204–213；web-app patch:45–63）。因此关闭模型外发或只看 Session 通道不等于没有其他出口。不得直接复制这些默认配置到合同/投研服务。

**验收。** 分页 500 边界及 SSE 断线重连不丢事件，读接口不新增模型调用/业务写入；事件内容脱敏；遥测未准入时外连哨兵为零。存储关键事务失败必须失败，遥测可选导出故障不能伪造业务成功或改变业务事务。代价是背压、保留期、观测存储与私密信息审查。

## 暂不吸收和必须保留的优势

不整体引入 Cordis/DSH 替换平台，不另造 Task/Gate/预算/沙箱。不默认启用 PTC、任意脚本、热安装插件、自动调度、无限重试、自动换 Provider、自动持久记忆或跨权限答案缓存。DSH workflow 的 `timeoutMs: null`、文件效果 sandbox 的非禁网边界和完整会话日志不能直接成为业务默认。

保留现有事务化终态和幂等、删除传播、metadata 控制、严格外部 Skill 包校验、禁网容器、默认关闭准入，以及协议反例测试。这些优势来自当前范围内的实现，不能扩大成全系统安全保证。

Dify 只借鉴概念与阶段组织：固定基线 LICENSE 是附加条款的 Apache 衍生许可，并非 MIT。DSH/Pi 与 SDK 包装层的 MIT 也不覆盖所有依赖、CLI 二进制及商标。本文不复制竞争项目源码；若将来直接复用包/代码，另核锁文件、许可证与产品使用方式，不把本报告当法律批准。

## 建议的三个最小交付包

| 顺序 | 交付范围 | 依赖与完成标准 | 明确不包含 |
|---|---|---|---|
| A 安全底座 | 第 1 项与第 4 项事件投影；fake CLI/sidecar 生命周期 | 合成秘密零事件泄漏、无启动注入；四种终止路径和归属异常有反例；版本兼容测试 | 真实模型、共享 CLI 目录自动清理、身份体系改造 |
| B 合同闭环 | 第 2、3、4 项：一个绑定 Public PDF 的 Pi 业务 Run，模型请求桥、只读 evidence 工具、候选 Artifact、人工交付 Gate | A 完成；离线模型发起工具调用并回读结果；预算/审批拒绝确实零执行；故障/取消/迟到候选不发布 | 不先接外部查询、不开放 bash、不新增 DSH 引擎、不宣称真实已验收 |
| C 检索与投研扩展 | 第 5、6、7 项；第 8 项按需要单独排期 | B 组件可复用，先完成非平凡评测；原生 Claude 路径仍遵守独立认证/预算边界 | 不凭代码支持启用 semantic/API，不把新流程自动扩展到所有业务 |

每个包在决定实施后再建 Work Item、版本化契约/ADR、迁移计划及验收脚本。本轮不改 tasks/state，不预批任务。真实模型、真实隔离执行、部署需各自证据；若需要改变身份/凭据/外发目的地，先停在边界上另行决定。线上 8765/132 必须检查发布身份后才能声称已具备某项能力。

## 复核入口与交付边界

审核请重点挑战：是否重复建设已有能力；工具/预算是否落在实际副作用之前；SDK 内部调用有没有被错误认定为可控；正文是否绕进事件/遥测；取消后清理是否误删或与子进程竞争；检索评测是否答案泄漏或单候选恒真；优先级是否能形成一个业务结果而非继续铺框架。

主要本地依据除正文定位外，包含 `docs/decisions/ADR-0040-pi-agent-adapter-boundary.md`、`ADR-0075-business-token-ledger.md`、`docs/harness/CORE_CONTRACTS.md`、`LOCAL_WORKBENCH.md`、`docs/research/COURSE_GAP_AUDIT_2026_10_04.md`。上游固定源码：[DSH](https://github.com/deepseek-ai/deepseek-harness/tree/5badb15009ae1756c3afe0ae0cef1faafc290ccc)、[Pi](https://github.com/earendil-works/pi/tree/f07218c4d4bbc12bef056a7058c3dd49dfe41abe)、[Dify](https://github.com/langgenius/dify/tree/3be01cbb7adae1ac34eece12e246c037962152ed)。DSH 官方仍将其定位为 [developer preview](https://www.deepseek.com/harness/en/)，本文不把预览代码当作生产适配承诺。

本文交付只有研究文档；不宣称完整源码审计、全量测试复跑、性能收益、真实供应商兼容或部署完成。SDK 修订方案及 DSH 讲解的复审与本报告分开，不用上游报告获批代替本方案审核。
