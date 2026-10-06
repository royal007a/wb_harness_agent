# DSH 过境收据（HA-0083）

依据 ADR-0083。仅升级平台与 DSH 子进程之间的私有协议，公开 Run 接口不变。

- 信封严格为 crossing_id + request，调用身份由平台签发，不接受模型原始 ID 作为票据。
- 工具票据绑定模型轮次、序号及工具名称/参数摘要。同一模型原始 ID 可以在不同轮次重复。
- 已完成同票同请求在活动 Run 内逐值回放内存中的首次响应；不走业务函数、预算、进展、工具/提交计数，不写新的事件。缓存与落盘收据不是断点续跑机制。
- 同票异参、未签发、错误命名空间、上一轮工具未完成、取消/截止后调用均拒绝。完整原始响应不持久化。
- issued / in_flight / completed / retired / unknown 以及摘要保存到 dsh_crossings；历史 failed 保留兼容。retired 只表示签发后未开始执行的票据被废止，不能计入已发送调用失败或费用。状态变化与 dsh.crossing 审计同事务。工具业务动作与完成收据之间并不构成一个跨 Provider 的原子事务；窗口故障保守 unknown，不重做。
- 重启终结未完成 Run，in_flight → unknown，issued → retired；预算 sent → unknown，不释放未知用量预留，不重发 Provider。历史 failed 不改写成 retired，历史事实不做推断迁移。
- HA-0085：正常成功/失败路径在写终态之前、同一事务内退役本次 generation 的未完成票据。成功路径还与产物发布、预算终态一起提交；故障时整体回滚。退役函数重复执行无写入，不影响其他 generation 或 completed/unknown/历史 failed 收据。
- 新 crossing 事件的 data.schema_version 为 dsh-crossing@2；外层通用事件 envelope 不变。没有该字段的历史事件按旧语义读取，不因为新投影而更改历史 failed。
- 取消不等待 crossing 锁或 Provider：Run 可以先进入 cancelled；在途回调返回后仍需记 unknown，finally 可退役未使用票据。因此取消之后或崩溃恢复时允许追加结算审计，不承诺所有场景的 Run 终态都是最后一条事件。退役不赋予回放权、不释放未知预算。
- 无自动 HTTP 重试；保护用于同一活动 Run 的重复投递。不提供网络 exactly-once、跨进程回放、A2 证据续跑或语义正确性保证。

测试：tests/test_dsh_crossings.py，包括线程并发、事务故障、预算 sent 恢复、真实 loopback HTTP（合成子进程），以及官方 DSH SDK + 合成 Provider（free/payment 两条路径）。旧对抗探针只适配信封；非法工具仍须被拒。
