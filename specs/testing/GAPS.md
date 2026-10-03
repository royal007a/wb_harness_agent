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

- 所有公开请求/响应与实际 OpenAPI/静态 OpenAPI/JSON Schema 一致性。
- 列表/详情的正反例、跨 scope、错误码、幂等、预算和状态变更后的读行为。
- 各浏览器入口与前缀、两端真实容器、修复后的重启/回滚与双端部署。
- 参考文档对照与过时 Current/README/历史 evidence 的声明纠正。
- 真实模型/外发/网盘账号相关能力须保留 gate；没做过的真实验证保持缺失。
- mymacclaude 对固定修复提交的独立 review。

本文件是开放问题清单，不意味着用上述样本替代用户的全部接口/功能目标。
