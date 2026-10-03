# HA-0060 Team 列表和 Snapshot 故障语义

1. 登记规格/ADR，HTTP复现四类列表吞503并保存旧版失败。
2. 实现明确的不可见错误白名单，Recovery先验证主体，Snapshot同样不吞故障。
3. 测试真实访问检查内部DB/数据错误、有效不可见状态、空/非空、隔离和事务回滚。
4. 相关/全量/verify证据，提交固定版本，交mymacclaude只读复审。
5. 本机兼容拓扑未获确认，真实双部署保持阻塞；不改8765/132/Provider。

代码检查点：旧5条行为反例失败；新增74项、相关174项、全量575 passed/16
skipped及verify通过；观察137/148，不是业务验收率。fff8d75已获独立Approved。
复审另发现非法status枚举被静默隐藏的Low，仍需后续规格与修复，不冒充已处理。
Evidence：harness/evidence/HA-0060/acceptance.md。
