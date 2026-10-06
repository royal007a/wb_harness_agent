# ADR-0086：有界 SDK 启动与阶段错误

状态：待复审。依据 HA-0084 的 H29（可诊断失败）、O15（总预算和期限），以及 HA-0085 隔离测试的启动超时实测。仅本地 DSH 8876，其他引擎不变。

## 问题

官方 SDK 0.2.1-alpha.1 的 initialize 20秒超时，被 bridge 统一隐藏为 DSH_RUNTIME_FAILED。HA-0085 多次在首次模型调用前失败，诊断确认 `RequestTimeoutError` 来自 initialize。原始 SDK 异常可含 stderr，不应直接向事件或前端传递。

## 决定

1. 明确区分 initialize 与运行。先 `await harness.start()`，再 `harness.run()`；SDK 的 start 缓存同一个成功握手，run内部再调用start不会重新初始化。失败即退出，不调用第二次start，不依靠SDK支持的重试行为。
2. initialize 独立等待上限从20秒改为60秒，缓解当前机器较慢的冷启动。它仍包含在创建Run时已冻结的总截止时间内，Python adapter持续check取消和截止，超时杀整个自有进程组；不会追加Run时间、模型调用或预算。60秒是保守工程上限，不是启动SLA或成功保证。
3. 在初始化阶段，SDK导出的 RequestTimeoutError 映射到固定 DSH_INITIALIZATION_TIMEOUT；其他初始化异常映射 DSH_INITIALIZATION_FAILED。运行阶段仍用 DSH_RUNTIME_FAILED；取消/Run截止优先。只传固定错误码，不传 SDK message/stack/stderr。
4. adapter只接受白名单、恰好type/code两个字段的错误信封；任何任意错误字符串或多余字段拒绝。平台网关已经记录的Provider/策略错误优先于子进程笼统错误，以免丢失原有超时/预算类别。
5. 不改变requestTimeoutMs=20000、不自动重试模型、不放宽工具、环境允许集合、日志投影、预算冻结和工作目录清理。

## 验收

SDK生命周期用离线mock分别验证初始化超时/失败/成功、运行阶段错误、取消；初始化失败不得执行run或重试，返回错误零原文。实际Python子进程验证私有协议白名单、取消/截止优先及清理；SDK+合成Provider复跑HA-0085、DSH回归和完整verify。各证据分层标注，最后才执行8876版本/PID绑定及浏览器/小额合成合同真实模型验收。
