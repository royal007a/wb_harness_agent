# 本轮验证缺口与修复队列

基线 b51dce6；以下为 HA-0053 实测发现，不是对全部功能的最终审计结论。

## 已复现的缺陷

| ID | 问题 | 证据/影响 | 后续验收 |
|---|---|---|---|
| RUNTIME-01 | cancelled Exchange 再进入 stream 会调用 Provider 并变为 succeeded | 合成 Adapter 探针：cancel 后 provider_calls=1，final=succeeded/done；当前真实模型 gate 关闭，因此未发生真实外发 | 取消前/中/后、Generator close、断线、终态不可覆写、无 assistant 持久化 |
| RUNTIME-02 | 同一 Exchange 并发 stream 可以调用两次 Provider | 同一 ID 两个 gather，合成 Adapter.calls=2，计数字段仍只能到 1 | 原子执行认领、重复消费者不触发调用、不取消原执行；重启清理 |
| OPENAPI-01 | Agent Lab 的 Schema 被 Agent Runtime 同名定义覆盖 | 合法 Lab model 请求 HTTP 201，使用已发布 OpenAPI 校验却报 provider_profile_id pattern 错误 | 命名隔离、合法/非法实例与 Schema 同集校验、所有引用可解析 |
| TEST-01 | Checkpoint 重启用例竞争 | 初始全量 1 failed：预期 failed 却为 running；测试启动后台 Worker 后又手动 execute | 注入阶段关闭 Worker；重启阶段只由真实 Worker 执行；已修复，定向及全量通过 |

以上 Runtime 探针为临时 SQLite + 合成 transport，外部网络调用 0；不是生产
事故或真实模型测试。修复不能只隐藏问题/修改声明，必须补行为回归。

### HA-0054 跟进（2026-10-03）

RUNTIME-01/02 已在 b639b8b 修复，912faca 双端发布；旧用例 13 failed，修复后
定向 76 passed；132 运行依赖 + 实际容器共 37 passed。独立 review 待收。
OPENAPI-01 仍未修复，26 未观测接口的全量验收仍未完成。

新发现 **UI-RUNTIME-01**：`frontend/agent-runtime.js` 的 `sendMessage` 先显示
SSE error，再由 `chooseSession → renderMessages(detail.messages)` 清掉错误；
没有 assistant 是正确的，但 Exchange 失败状态也没有被呈现。实际远端截图
只有 user 消息，源码确认 detail.exchanges 被忽略。浏览器测试只在瞬间断言
error，reload 后只验证 Session 存在，所以脚本绿灯漏掉了持久错误展示。
后续必须单独显示 Exchange 状态（不能伪造 assistant），并在发送完成、重新
选择会话及刷新后验证错误仍可见，不能只等到瞬时文本出现就通过。

**PROVIDER-01**：2026-10-03 用 httpx.MockTransport 只发一段 delta 后 EOF，
不发送 `[DONE]` 或 finish_reason。Adapter 产出 1 个片段后正常结束，未报错；
已从源码风险升级为协议层复现，但尚未验证 Product Run/Exchange 最终发布路径。
没有真实外部请求，真实 Provider 继续不准入。需独立规范和回归修复。

### HA-0055 跟进

UI-RUNTIME-01 的旧浏览器稳定断言已失败复现；Exchange 独立状态卡、选择代次
和发送所属 Session 已补齐。全量验证 337 passed / 16 skipped；新增流中预览
断言后的补充浏览器回归及双端部署记录以 HA-0055 Evidence 为准。独立 review
未通过前不将本条标为最终验收。此处没有修复 Provider 上游 EOF 或 OpenAPI。

HA-0055 手机视觉复核另外发现内部列裁切：document 宽度正常，但消息列
超出视口。已补双边界反例，1840639 修复；14 项 UI、全量 340 passed / 16
skipped，正式发布 Evidence 继续记录。

**DEPLOY-01**：1840639 本机 reload 时，bootout 后固定 1 秒就 bootstrap
返回 5；同样的自动 plist 回退也失败，后续手动 bootstrap 才恢复。数据库备份
完整，health 和 gate 已复核；不能宣称自动恢复通过。需用有界 teardown/
bootstrap 重试和失败注入测试修复发布助手（不擅自强杀其他服务或回滚 DB）。

HA-0056 已实现有限重试及健康恢复，冻结392e103全量356 passed/16 skipped。
真实发布前本机 GUI domain 不可用（125）且8765离线，等待用户恢复图形会话；
132 保持1840639。代码通过不等于两端发布完成，故本问题仍开放。

2026-10-04 独立复核更正：HA-0053/0054 Approved；HA-0055/0056 Changes Requested。
0055 待补流中停止的有界回查与停止按钮 Session 归属；0056 的 exit 5 不必然
暂态，必须在 bootout 前预检会话域并在健康检查绑定进程/发布身份。调用方
Background 是 125 候选根因，不能要求用户重新登录后就保证恢复；同 uid user
域加 Aqua/Background plist 是尚未采用的备选，不能静默换 system/root。
HA-0053 的 Low：清单生成器在符号链接 PYTHONPATH 下 relative_to 可失败；
observed 仍包含拒绝的 4xx，不等于 observed_2xx_passing 或业务成功。

继续文档对照时需处理 `CURRENT_ARCHITECTURE.md` 重复的 Memory 段落，以及
“尚未具备”列表与文首已实现离线 Adapter 的粒度冲突；用逐能力状态替代笼统
未实现。部分评测的 `external_execution_calls=1.0` 是通过分数而非调用次数，
需明确指标命名/口径，避免与顶层 `external_calls=0` 混淆。

## 接口基线

2026-10-04 最新跟进：HA-0055 2f8a30c 与 HA-0056 ce490c5 **代码已独立 Approved**，
上述历史 Changes Requested 已返工；真实双部署仍未完成。PROVIDER-01 在
HA-0057 已扩展到真实 Adapter→Exchange/HTTP 路径：旧4反例确实误发布 done，
新协议要求 stop+DONE，56项协议回归及全量446 passed/16 skipped，85fc7d3已独立
Approved。复审指出压缩响应在限额检查前内存放大，追加修复为读取前拒绝编码，
不因此宣称第三方兼容或已部署；补丁验证记录见HA-0057 acceptance。
OpenAPI 同名 Schema 和未观测接口队列仍开放，不因局部通过而收口全系统目标。

148 个方法/路径组合（包含 HEAD、页面、静态 mount），22 类功能。
观察器全量运行：307 passed、16 skipped，122 个入口被测试请求命中，26 个
未观察到。明细在 `harness/evidence/HA-0053/http-observations.json`。

其中多数缺口是 list/read API：Lab/Runtime 列表、Memory Bank 列表、研究列表、
Team Session/Agent 列表、资源读取及 Replan 列表；另外 Workspace 创建/成员
授予的 HTTP 路径尚无观测（内部方法测试不等于端点测试）。全部需补 HTTP
正反例。122 个 observed 仍需逐项检查断言，不能直接标为验收通过。

### HA-0058 跟进（2026-10-04）

OPENAPI-01 的同名覆盖已修复，待固定提交独立 review 与部署验收：三个冲突域
隔离命名空间，21 份契约注册拒绝异义重名；Lab/Runtime 现有聊天 API 补齐响应
合同并对照静态、动态 Schema 验证实际 HTTP 实例。旧版 7 个行为反例失败；
26 项新增测试、相关 101 passed；完整 verify 为 483 passed/16 skipped。

最新全量观察器：131/148 observed，17 未观测；其中 130 个入口有 passing test
的 2xx，剩余已观测的 Channel 详情只有 403。这些数字均非业务验收率。
结果见 `harness/evidence/HA-0058/full-http-observations.json`，源码哈希在运行前后
一致；报告固定基线 cd9b113 + 当时未提交修复，不冒充基线自身的结果。

尚未观测的入口：Memory Bank / Recovery / 三类 Research 列表、sample、
Team runtime / sessions / workspace agents、health、resources 列表与详情、
Run replans、OpenAPI/静态 HEAD，以及 Workspace 创建/成员授予。
0057 编码修复986ed1d已独立 Approved，但0055–0058均没有本轮双端发布证据。

### HA-0059 检查点（2026-10-04）

新增 **TEAM-READ-01**：Channel撤销成员、归档或降低clearance后，详情拒绝但
列表仍返回ID/标题；2bd4af8旧3反例均失败。列表现复用详情的当前授权检查，
过滤明确不可见项、意外错误继续上抛；新增18个HTTP用例，相关44项、全量501
passed/16 skipped。包含Workspace创建/成员授予幂等、跨Workspace读取、
Session owner/channel过滤、历史与撤销重启，不新增身份认证或在线撤销API。
代码待review，真实双部署未验收。

最新 `harness/evidence/HA-0059/full-http-observations.json`：136/148 observed，
且136个都有passing-test的2xx；仍然不是业务验收率。12个未观测入口是：Memory
Bank/Recovery/三类Research列表、sample、health、resources列表/详情、Run
replans、OpenAPI/静态HEAD。它们继续待做，完整功能/错误路径也仍需逐项核对。

### HA-0060 检查点（2026-10-04）

HA-0059已独立Approved；复审发现既有 **TEAM-READ-02**：Session/Task/Inbox/
Recovery列表把503吞成空列表；同类问题也在Session Task snapshot中。
HA-0060按明确(code,status)白名单修复，Recovery扫描前校验actor。旧5个行为
反例失败，新增74项、相关174项、全量575 passed/16 skipped，verify通过。
覆盖内部DB/字段故障、合法不可见状态、未知/暂停主体、scope错误和事务回滚；
不是身份认证，也不改变GET既有惰性过期机制。待固定提交独立review与双部署。

观察器137/148且有passing-test 2xx的入口137个；11未观测：Memory Bank、
三类Research列表、sample、health、resources列表/详情、Run replans、
OpenAPI/静态HEAD。Channel持久列/JSON Workspace不一致的Low另待处理。

## 尚未完成的端到端验证

### HA-0061检查点（2026-10-04）

新增57个参数化测试项，相关123 passed，全量632 passed/16 skipped，verify exit0。
full-http-observations.json记录148/148 observed，148都有passing-test 2xx；未观测
入口从11归零。只补TestClient行为/临时DB验证，公开响应Schema仍有缺口，全部分支、
浏览器/容器/真实模型/双部署均不能由该数字证明。固定提交待独立review。

### 2026-10-04 独立review追加及HA-0061范围

- HA-0058（2bd4af8）与HA-0060（fff8d75）代码均已独立Approved，历史“待review”
  已被本检查点取代；两端发布状态并未改变。
- **OPENAPI-02 / Low**：投影递归会修改const/enum/default/examples里作为字面数据
  的$ref；当前spec没有触发，不代表helper对未来契约安全。后续跳过数据关键字并
  补嵌套实例回归。
- **RUNTIME-STATUS-01 / Low**：Runtime status中model_calls/provider_calls/
  network_calls固定0，是静态声明而非计数；不能用作无外发证据。
- **TEAM-READ-03 / Low**：非法status枚举（None/ACTIVE/actve）被当作非active
  静默过滤；现有损坏字段测试未覆盖此形态。应区分合法非active和未知状态。
  Channel列表仍未改用共享(code,status)规则；其持久列/JSON workspace分歧也仍在。
  HA-0063（116a164）已独立Approved：五类Foundation行结构/枚举+SQL键校验、共享
  过滤；尚未实际部署，不是全库扫描或自动修补。
- **TEAM-STATE-02 / Low**：合法归档可能先短路，关联membership未被读取，不能称
  所有关联记录在任何访问决定之前都已校验。Channel列表的提前membership校验
  缺“归档+坏membership”组合反例（该行删除突变存活）。Workspace同类短路仅
  为reviewer读代码推断。SQL channel.workspace_id改走时，旧scope列表JOIN选不到
  会静默漏行，详情才500；规格已明确该边界，回归缺口后续处理。
- **TEAM-REPLAY-01**：HA-0063审查时用临时DB实测，Session创建首次201，Channel
  归档后detail与新key均409，原key却返回201且与首次缓存body相同。
  `_idempotent`在action当前资格检查之前返回缓存；应单独核对Team所有写路径
  的重放授权，不把“没有重复写入”当作“允许返回旧数据”。HA-0064候选已在25个
  写入口增加事务内只读授权，287新增/526相关/1035全量通过，0ee58a0已独立
  Approved，等待实际部署；不是HA-0063的新key
  写入拒绝证据，无正式DB变更或真实Provider验证。
- **TEAM-REPLAY-02 / Low**：HA-0064复审发现两处存活突变：channel_grant归档后
  重放的专用负例缺失；读取收据与授权必须同一事务的条款也没被回归锁定。
  当前代码行为正确，未发现生产缺陷；不以串行DB不变证明并发撤销线性化。
  部分grant/agent binding只比较原body/path，缺历史上游快照的限制继续保留。
- **READ-SCHEMA-01**：health、resources列表与单项详情、Memory Bank列表、三种research列表的
  公开成功响应Schema缺失或为空占位。HA-0061字段断言只补行为验证，不冒充已经
  补齐公开机器契约。sample实际是text/csv，旧动态文档却声明application/json和
  空Schema。资源本地登记元数据不等同未来平台Resource对象。HA-0062在代码中
  对齐核心Product/health/resources/sample；Memory及三类research列表仍未补齐。
- **HEAD-TEST-01 / Low**：HA-0061独立Approved，32突变杀死31处。HEAD空正文
  断言由TestClient/传输层保证，不能证明应用ASGI未发送body；证据措辞已修正。
- **SCHEMA-FORMAT-01**：当前venv通用FormatChecker未安装可选date-time检查依赖。
  HA-0062显式校验本地服务实际UTC输出格式及非法日期；其他测试不能据仅传入
  FormatChecker就宣称已验证日期语义。未将本测试用UTC子集当通用RFC3339校验器。
  HA-0062独立review另发现检查器自身缺naive/非UTC负例。HA-0065已补Schema层
  正反例并修复24:00:00被解析器归一化后误放行；候选待独立review与部署。
- **PRODUCT-CONTRACT-02 / Low**：HA-0062（7ac1498）已独立Approved，21突变杀死17个；
  动态422信封绑定删除、Task详情required去掉runs、retryable放宽为boolean仍未
  被测试杀死；HA-0065已补精确负例且3个对应突变均被杀死，候选待review。
  before.xml来自未单独保存源码的早期19项测试，不是
  当前52项可原样复现的基线报告；acceptance/review已明确限制。
- **PRODUCT-CURSOR-01 / Low**：事件after声明minimum=0却无SQLite整数上限；
  after>=2^63会500，合法声明值和运行时不一致。HA-0065候选已统一0..2^63-1，
  HTTP入口及Store双重拒绝越界，静态/动态/源Schema一致，边界/+1已通过，待review。
- **PRODUCT-REF-01 / Low**：Event.run_id/task_id、Artifact.run_id缺格式约束；
  可接受错误ID前缀。HA-0065候选已补Product格式及12个反例；仍不等于核对跨对象
  引用一致性或运行时逐响应校验，待独立review与实际部署。
- **REQUEST-ID-01 / Low**：Problem/校验错误body request_id与X-Request-ID不一致，
  middleware直接拒绝又缺该头；未有统一承诺。需先定义追踪合同再覆盖所有错误路径。
- **PRODUCT-CONTRACT-03 / Low**：HA-0065独立Approved（e6e1fb9）；复审核实旧28
  行为反例及112项测试。后续补23:59:60向量；Product ID的`$`在Python校验器可
  放过末尾换行，需跨语言正则边界审计，不能直接改Python专有锚破坏ECMA兼容。
  以上0065历史“待review”由此取代，真实双部署仍未完成。
- **READ-SCHEMA-01 后续HA-0066**：Memory runtime/Bank列表详情创建、三类Research
  列表共7项候选已补实际响应合同。根Run可省略parent_run_id或为null；Memory
  FTS退化与semantic档案异常仍是合法状态。其他研究写入/详情、Pi等空Schema未
  纳入，不称全系统OpenAPI完整；待固定提交独立review与双部署证据。
- **OPENAPI-EMPTY-03**：HA-0066后程序枚举仍有35个API成功响应的application/json
  Schema恰为空对象，另有1个页面。明细见HA-0066/remaining-empty-responses.json，
  包括Pi、研究创建/详情、Memory写入、Recovery等；不统计缺content或非空但不完整
  的Schema，因此不是全部缺口计数。后续必须继续补实际实例/负例，不用148入口观测替代。
- **EVIDENCE-PATH-01**：HA-0063收口时全量任务引用检查发现历史HA-0027仍引用
  不存在且未被Git跟踪的harness/evidence/HA-0027/l3-admission-gate.json。
  注册表Schema合法不等于所有历史证据可取回；未生成替代证据，待追查原记录。
- HA-0061限定剩余11个读取入口的内容、状态、拒绝与持久性测试，不改业务实现。
  原生研究非空列表来自临时测试准入元数据，stream哨兵禁止执行SDK。PDF登记样本
  只有测试头部，不是完整PDF解析/真实研报证据；health是静态响应，不是release验证。

- 所有公开请求/响应与实际 OpenAPI/静态 OpenAPI/JSON Schema 一致性。
- 列表/详情的正反例、跨 scope、错误码、幂等、预算和状态变更后的读行为。
- 各浏览器入口与前缀、两端真实容器、修复后的重启/回滚与双端部署。
- 参考文档对照与过时 Current/README/历史 evidence 的声明纠正。
- 真实模型/外发/网盘账号相关能力须保留 gate；没做过的真实验证保持缺失。
- mymacclaude 对固定修复提交的独立 review。

- **MEMORY-READ-02 / Low**：HA-0066固定5429c62独立Approved。后续补sources负计数、
  semantic external_calls负数、keyword不可用/error=null三条专门反例，生产约束
  已有但删除突变存活。非UTF-8准入档案仍会500（既有问题，需另项修复）；
  静态POST /local/research和GET /local/research/{runId}仍缺。上述0066待review已解除，
  真实双部署未完成，不把已有信封校验说成档案故障已恢复。
- **OPENAPI-EMPTY-04**：HA-0067补Pi runtime与四个离线管线响应，剩余明确空
  JSON成功声明为30个API加1个页面（本项remaining-empty-responses.json）。
  Pi Product Run五入口仍在，缺content或非空但过宽合同仍不计入此数。
- **PI-HTTP-01 / Info**：离线管线保留原有请求投影、流key上限120、Accept
  子串检查与两次独立收据事务；不是严格内容协商或流结果原子持久化承诺。
  本次公开当前行为并测试，不把metadata guard的allow误当实际执行授权。

本文件是开放问题清单，不意味着用上述样本替代用户的全部接口/功能目标。
