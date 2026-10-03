# Team 列表故障不得伪装为空（HA-0060）

范围：Session、Task、Inbox、Recovery Case 列表，以及 Session detail/handoff
中的 Task snapshot。沿用 metadata-only 协议身份，不新增认证或执行权限。

## 契约

1. 列表在扫描数据前验证 actor：缺失参数422；不存在404/TEAM_AGENT_NOT_FOUND；
   suspended403/TEAM_AGENT_SUSPENDED，即使库中没有条目也不能返回成功空列表。
2. 逐项访问检查只允许过滤下列 `(code,status)`：
   - TEAM_CHANNEL_ACCESS_DENIED / 403
   - TEAM_WORKSPACE_ACCESS_DENIED / 403
   - TEAM_DATA_CLEARANCE_DENIED / 403
   - TEAM_CHANNEL_ARCHIVED / 409
   - TEAM_WORKSPACE_ARCHIVED / 409
   Task 的历史无绑定条目额外允许 TEAM_TASK_LEGACY_UNBOUND / 409；不能把此例外
   用到 Session/Attention。明确指定 channel 的请求仍在扫描前直接拒绝不可访问的
   Channel，而不是返回空列表。
3. 其他 Problem 保留错误码/status；DB 异常、损坏字段、scope 不一致不转成空列表。
   错误响应不能返回部分 items；故障导致事务中止，已有惰性到期写入也应回滚。
4. 可访问项保留当前次序、owner/target隔离、运行状态与既有响应Schema。
   在混合列表中隐藏某项不能删掉其他可见项。恢复列表继续按 Task 可见性展示；
   不把它误称为 owner-only，也不改变 detail 的 contributor/coordinator 约束。
5. Inbox lease / Recovery deadline 的惰性过期是既有行为，不宣称 GET 无写入。
   本轮只增加 Recovery 扫描前的 identity 检查，不重新设计到期机制。

## 验证

通过公开 HTTP 在临时 SQLite 创建全部对象。旧版至少对四个列表的503探针失败；
新增负例逐个断言准确错误码和无 items；在真实访问检查内部注入DB/数据故障。
逐项覆盖合法不可见状态、正常非空/空、未知/暂停actor与历史Task例外。
补 Session snapshot 故障与事务回滚；相关回归、全量观察器、verify 分别报告。
固定提交交独立review；部署仍须本机→132，未解决本机拓扑前不冒报发布。

非目标：修复历史数据列/JSON scope分歧、改变Snapshot业务选取范围、JWT认证、
真实模型/工具、缓存、所有HTTP契约和12小时整体目标完成。

## 已知未满足边界（fff8d75独立review）

第3条是目标约束，不代表已验证全部损坏形态。非法status枚举None/ACTIVE/actve
仍被既有非active检查按不可见项过滤；只有缺字段、非法JSON/clearance等已列明
形态会返回故障。后续应校验合法枚举再判定可见性，不能把该Low说成已经修复。
Channel列表不在本规格的四列表范围中，仍使用旧code-only规则，另有统一待办。
