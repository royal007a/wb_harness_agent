# Team HTTP 列表与当前协议授权（HA-0059）

范围：Workspace 创建/成员授予、Workspace Agent 列表、Channel 列表/详情、
Team Session 列表与运行状态。补 HTTP 正反例，不新增登录或撤销管理 API。

## 必须满足

1. Workspace 仅 local_admin 可创建；授予成员需当前 owner/admin、目标身份已存在、
   合法角色与 clearance。幂等重放不重复创建，换 body 同键拒绝；拒绝后状态不变。
2. 非成员不能读取 Workspace Agent 列表；已有成员可读取该 Workspace 的身份目录。
   身份目录是管理元数据，不等价于“可调度且 active 的 Agent 清单”。
3. Channel 列表不得旁路详情授权。返回项必须同时满足 active identity、active
   Workspace 与 membership、足够 clearance、active Channel 与其 membership。
   撤销成员、降低 clearance 或归档后，列表不再返回其 ID/标题；详情继续拒绝。
   合法空列表返回200；无效主体或无 Workspace 资格应显式拒绝。
4. Session 列表只列 actor 自己且当前可访问的 Session；无 channel 过滤时逐项
   检查权限，指定 channel 时先检查该 Channel。不同主体/Channel 不混入。
   retired Session 可作为历史保留，但不能越过当前可见边界。
5. HTTP actor_id 只是协议参数，不是登录证明。runtime 明示 not_connected/零外部
   调用，测试不使用真实 Provider/凭证，不自动扩大权限或触发工作。

## 验证

- 公共 HTTP 创建两 Workspace、多个 Agent/Channel/Session，验证空/非空、角色、
  跨 scope、缺参数、不存在对象、幂等与错误码。
- 用临时 DB 注入满足现有 Schema 的 revoked/archived/clearance 变化，模拟既有
  状态恢复；这是状态故障注入，不代表已实现在线权限修改 API。
- 旧2bd4af8必须在撤销、归档、降级三组 Channel 列表探针上失败；详情为拒绝而
  列表仍泄露标题的差异不能靠修改断言消除。
- 验证已有动态响应合同；完整回归与接口观察器分别报告，不把2xx当业务验收率。
- 固定提交独立 review。真实部署仍需本机→132，本机拓扑未定时如实记录阻塞。
