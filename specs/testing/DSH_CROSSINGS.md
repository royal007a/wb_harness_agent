# DSH 过境收据（HA-0083）

依据 ADR-0083。仅升级平台与 DSH 子进程之间的私有协议，公开 Run 接口不变。

- 信封严格为 crossing_id + request，调用身份由平台签发，不接受模型原始 ID 作为票据。
- 工具票据绑定模型轮次、序号及工具名称/参数摘要。同一模型原始 ID 可以在不同轮次重复。
- 已完成同票同请求在活动 Run 内逐值回放内存中的首次响应；不走业务函数、预算、进展、工具/提交计数，不写新的事件。缓存与落盘收据不是断点续跑机制。
- 同票异参、未签发、错误命名空间、上一轮工具未完成、取消/截止后调用均拒绝。完整原始响应不持久化。
- issued / in_flight / completed / failed / unknown 以及摘要保存到 dsh_crossings；状态变化与 dsh.crossing 审计同事务。工具业务动作与完成收据之间并不构成一个跨 Provider 的原子事务；窗口故障保守 unknown，不重做。
- 重启终结未完成 Run，in_flight → unknown，issued → failed；预算 sent → unknown，不释放未知用量预留，不重发 Provider。
- 无自动 HTTP 重试；保护用于同一活动 Run 的重复投递。不提供网络 exactly-once、跨进程回放、A2 证据续跑或语义正确性保证。

测试：tests/test_dsh_crossings.py，包括线程并发、事务故障、预算 sent 恢复、真实 loopback HTTP（合成子进程），以及官方 DSH SDK + 合成 Provider（free/payment 两条路径）。旧对抗探针只适配信封；非法工具仍须被拒。
