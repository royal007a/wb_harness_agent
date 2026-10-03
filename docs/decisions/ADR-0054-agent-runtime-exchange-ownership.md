# ADR-0054：Exchange 唯一执行权与终态保护

- Status: Accepted for isolated runtime repair; external execution remains gated
- Date: 2026-10-03
- Work item: HA-0054

## 问题与决策

HA-0053 在合成 Adapter 上复现 cancelled 被改成 succeeded、两个 stream
消费者重复调用 Provider。ADR-0022 的取消与幂等保证未落实，先修生命周期，
不把独立聊天 Runtime 顺势升级成 Agent Loop 或 Product Run。

1. 一个 Session 最多一个 queued/streaming Exchange。已有幂等键优先重放；
   新键遇到活动 Exchange 返回 HTTP 409 `SESSION_BUSY`，不写用户消息。
2. SQLite `BEGIN IMMEDIATE` 内原子领取 queued → streaming；只有领取者可
   执行。其他消费者只得到 SSE error `EXCHANGE_IN_PROGRESS`，不能终结、
   取消或重新调用原执行。终态重放不解析凭证、不调用 Provider。
3. cancelled 重放为 `EXCHANGE_CANCELLED`；failed 重放持久错误码；succeeded
   重放原消息。SSE 计数是该 Exchange 的持久调用尝试数，不是重放新增费用。
4. Provider 开始前计数 0，获准准备调用时在事务内计数 1（尝试数，不保证网络
   已发送）。取消与最终 assistant 写入在同一数据库锁下裁决：取消先提交，
   则不得发布 assistant；成功先提交，之后取消不撤销已完成结果。
5. owner 消费者关闭或被取消时，关闭上游异步生成器，未终结 Exchange 标记
   cancelled。非 owner 的断线不能取消 owner。每 100ms 检查持久取消状态；
   活跃异步 Provider 总等待上限 90s，累计输出最多 12000 字符，与消息契约
   一致。超时/超长分别 `MODEL_PROVIDER_TIMEOUT` / `MODEL_OUTPUT_LIMIT`，
   无部分 assistant 入库。同步凭证解析与不协作的自定义 Adapter 不具备 OS
   级抢占保证；消费者背压暂停期间，恢复消费时重新检查绝对 deadline。
6. 服务启动拿到独占数据库锁后，把残留 queued/streaming 标记 failed /
   `MODEL_RUNTIME_RESTARTED`；不重放外部操作。用户可用新幂等键主动再发。
7. context 截至该 Exchange 自己的 user_message.sequence，最多 2N 条，
   不把别的未来请求并入上下文。

## 边界与兼容

不增加公开取消 API，不迁移表；原有状态和 SSE 类型兼容，新增明确错误码。
HTTP 连接断开只保证本进程请求取消和不发布结果，不能保证 Provider 停止计费。
不启用真实模型、不注入工具/Skill、不写 Product 状态，不宣称费用硬上限已实现。
修复按旧实现失败 → 新实现通过的测试记录、双端部署、独立 review 验收。
