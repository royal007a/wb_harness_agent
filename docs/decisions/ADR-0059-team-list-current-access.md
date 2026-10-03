# ADR-0059：Channel 列表复用当前详情可见性

状态：8a7e840获独立代码Approved；真实双部署仍阻塞。
HA-0059，基线2bd4af8；证据见 harness/evidence/HA-0059/acceptance.md。

## 实测问题

撤销 Channel membership 后，详情返回403/TEAM_CHANNEL_ACCESS_DENIED，
Workspace channels 列表仍返回被撤销 Channel 的 ID、标题与元数据。
列表只做 SQL join，没有检查逐项 membership status、Channel status 或 clearance。

## 决策

保留当前单用户 metadata-only 控制面和 actor_id 协议身份，不引入认证。
列表先核对 identity/Workspace，再逐项复用 assert_channel_access；对明确的
不可见项过滤，其他错误不能静默伪装为空列表。详情保留已有错误码。
不修改 Agent 身份目录语义（目录不承诺目标身份均可执行），不新增撤销管理API。

用已登记状态故障注入验证撤销、归档、clearance下降，并补 Workspace写路径、
成员/Session读路径的HTTP证据。见 specs/testing/TEAM_READ_VISIBILITY.md。

独立复审指出其他列表和Session snapshot仍可能吞掉Problem，HA-0059没有修复
这部分；由ADR-0060另行定义一致的错误分类和HTTP故障验证。
