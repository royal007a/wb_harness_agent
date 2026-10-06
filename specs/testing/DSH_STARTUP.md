# DSH启动期限（HA-0086）

- 固定SDK版本不变。initialize单次上限60000ms；SDK start成功后run复用握手，不重发初始化。失败退出，无自动重试。
- 上限不是额外时间额度：整个子进程生命周期始终受Run原有截止和取消控制。启动失败未发生模型发送时，账本calls/spent/reserved为0；若已经发生调用则以实际账本为准，错误类别不得据此解冻unknown。
- 仅初始化阶段RequestTimeoutError为DSH_INITIALIZATION_TIMEOUT，其他为DSH_INITIALIZATION_FAILED。运行期错误不是初始化错误。
- 错误信封恰好包含type='error'与固定code，不允许message/stack/任意字段。原始异常只在合成诊断期间临时查看，发布代码仍丢弃stderr。
- adapter先检查取消/Run截止，再保留平台网关已有错误，最后读取子进程固定类别。原有Run终态不可覆盖。
- 不把启动成功算成Provider就绪，不把只跑mock算成真实SDK/部署验收。
