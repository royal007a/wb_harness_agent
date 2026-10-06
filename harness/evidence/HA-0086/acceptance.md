# HA-0086 启动阶段分类：交审证据

基线 `1ae1a6a`；第二批课程文档提交 `97a0772` 不改变运行代码。本切片只改私有 bridge 生命周期、adapter 固定错误协议和验证，不改 SDK 版本、Provider、预算或公开请求 Schema。尚未部署；全量 verify 正在串行运行，最终结果另补，不能据以下定向通过宣布已验收。

## 动机与实现

HA-0085 隔离测试曾多次在首次模型请求前失败。短暂的合成诊断确认是 SDK initialize 的 `RequestTimeoutError`（20000ms），不是 Provider 或退役事务；诊断代码已撤回。没有证明机器负载是根因。

`lifecycle.mjs` 明确先 start 再 run；固定 SDK 的 start 缓存成功初始化，run 内部 start 复用同一握手。初始化单次等待60秒，Python仍持续检查取消和Run截止，不增加任务总时间或重试。初始化超时、其他初始化失败与运行失败分开；原始message/stack/stderr不转发。SIGTERM清理promise的拒绝也被丢弃，避免异常正文变成未处理拒绝。

adapter仅接受恰好type/code的白名单信封。它先检查Run取消/截止和网关已有错误，再映射子进程固定错误。子进程的DSH_CANCELLED只是失败类别，不授权覆盖平台已持久化的终态。requestTimeoutMs仍是20000；send/unknown预算语义未动。

## 已执行

新文件 `tests/test_dsh_startup.py` SHA-256：`2825949c626d7cb2b48eb3ca729e445d01d8e54793fc91560b9bdd720baaab99`。

| 命令/层级 | 结果 | 证据 |
|---|---|---|
| 新文件（Node离线SDK对象 + 实际Python子进程 + 临时SQLite） | 16 passed | startup.xml |
| 新文件、crossing_retirement、crossings、ha0082_review_probes、workbench五文件；包括真实DSH SDK加合成Provider | 114 passed，553.19秒 | targeted.xml |
| 在同一解释器中仅将DshAdapter换回1ae1a6a版本，跑fixed_child_error/startup_failure选择器 | 5 failed / 1 passed / 0 errors | before-adapter.xml |

基线是**adapter单模块对照**，不是旧版本全套或旧SDK启动时间实验。用git show获取旧源码，内存加载为adapters子模块，保留真实__file__和包名；其他源码不改。失败均为实际错误类别断言：原版将初始化超时/失败和中断统一报DSH_RUNTIME_FAILED；新增分类正确返回。没有把不存在新helper的导入失败当反例。

新测试分别验证：初始化失败后不run也不重试；普通Error伪造name不冒充SDK超时类型；运行期超时不冒充启动错误；原始合成秘密不留在包装异常；固定错误、多余字段、未知code、非对象；等待启动时取消/截止能在5秒测试上界内杀子进程并清目录；网关预算错误优先；启动失败calls/spent/reserved均为0且无产物。后者只针对未调用模型的路径，不意味着任何失败都可解冻预算。

一次测试脚手架修正：urllib在本机可能读取系统代理，最初网关优先级探针未到达loopback。测试改为显式ProxyHandler({})并断言实际回调收到一次请求；生产HTTPX仍原有trust_env=False，不是为测试放宽网络策略。

## 定向突变

| ID | 单点变化 | 行为断言结果 |
|---|---|---|
| M1 | 不执行显式start | 1 failed / 0 errors：初始化失败类别与调用顺序不符 |
| M2 | 所有初始化异常归普通失败 | 1 failed / 0 errors：SDK超时分类不符 |
| M3 | 运行期错误归初始化超时 | 1 failed / 0 errors：运行阶段分类不符 |
| M4 | 包装错误携带合成秘密 | 1 failed / 0 errors：stack原文检查失败 |
| M5 | 接受错误信封额外字段 | 2 failed / 4 passed / 0 errors：message/stack未被拒绝 |

每项对应M1–M5.xml。均已恢复源码；全量verify在恢复后才启动。不称为全库mutation score，也不把一次定向通过称为长期稳定性。

## 尚待

- 完整verify最终结果、独立复审、8876部署及真实Provider小额合成合同冒烟。
- 60秒是有界容忍，不保证所有机器启动成功；SDK清理期间如果把原错误包装为AggregateError，会被归为固定INITIALIZATION_FAILED，而非猜测内部消息分类。
- 启动失败的根因只定位到initialize超时；未对上游内部模块耗时逐项分析。
- 本切片没有测试OS沙箱、第三方网关兼容、外部连接或跨进程恢复的额外保证。

XML经结构化解析后，仅规范化机器路径、主机名与行尾空白，再解析验证；保留初次失败和突变的真实结果。未保存课程全文、凭据或真实合同。
