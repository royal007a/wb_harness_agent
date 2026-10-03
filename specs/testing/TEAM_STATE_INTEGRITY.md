# Team Foundation 持久记录完整性（HA-0063）

基线7ac1498。HA-0060区分权限拒绝与存储故障，但未知status仍被当作合法非active，
Channel列表按code而非(code,status)过滤，列与JSON的scope也可分歧。

## 合同

1. 五种Foundation记录（identity/workspace/channel/两类membership）读取时先校验
   现有Schema的结构、类型、枚举、必填与额外字段，再检查主键/关联键与所选SQL行一致。
   无效JSON、未知status（含null/ACTIVE/拼写错）、非法角色、列/JSON身份或scope分歧
   返回500/TEAM_STATE_CORRUPT。消息固定，不回显损坏正文、身份、标题或SQL。
2. 只有验证后的合法inactive才能触发原有语义：suspended为403、archived为409、
   revoked为403或逐项隐藏。不存在仍用既有404；无membership仍403，不变成损坏。
3. Channel列表与四类列表共用(code,status)过滤。请求级Workspace资格仍先检查，
   不可因逐项过滤变成成功空列表；未知/错误status组合必须上抛，不返回部分items。
4. Workspace列表、身份目录、Workspace/Channel详情的membership数组也不直读
   未校验JSON。身份目录保留原有管理语义：合法suspended身份与revoked成员记录
   可以列入目录，不等于可执行或有授权。
5. 同一事务内发现损坏即失败；禁止自动修补、改名、撤销、重新归属或删除记录。
   失败回滚包括既有Inbox/Recovery惰性过期；不新建模型/工具工作。

## 非目标与可验收边界

不是认证体系或数据迁移，不扩大权限。只校验实际读取到的Foundation行，不是
全库完整性扫描（JOIN未选到的孤立行不因此被发现），也不验证内容真实性或所有
跨模块对象。日期format注解不在此检查器的语义范围；时间先后另由原业务检查。
例如只改Channel的SQL workspace_id而JSON仍属旧scope，旧scope列表选不到该行，
可以返回空；详情实际读取后才报500。合法archived也可能先短路，后续membership
未被读取，因此不承诺“所有关联行在任何访问决定之前均已校验”。Channel列表提前
校验membership的组合状态回归尚缺，见HA-0063/review.md的L1。
HA-0063没有解决旧幂等键绕过action授权的TEAM-REPLAY-01；后续HA-0064的实现与
验收见TEAM_REPLAY_AUTHORIZATION.md，不把本轮新key测试当成缓存重放证据。
现有合法输入与数据的HTTP行为不变；坏持久数据从403/409/空列表改成500是明确
兼容性变化。Schema版本升级需先迁移并审查，不容忍未知版本静默继续。

先在旧版运行HTTP反例：5种对象未知状态、Channel列/JSON错域、code相同status不同。
再覆盖合法inactive、detail/目录、缺字段/非法JSON/类型、主键绑定、无部分结果、
事务回滚、写操作拒绝不变；定向/全量/verify并固定提交独立review。
所有测试临时SQLite，禁止真实Provider、正式DB、8765、132及凭据。真实发布仍
按本机→132；本机拓扑未明确之前不报已部署。
