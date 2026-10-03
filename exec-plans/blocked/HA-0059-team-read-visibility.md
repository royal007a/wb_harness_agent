# HA-0059 Team HTTP 可见性与缺口回归

目标：补 Team 未观测接口，修复列表/详情当前权限不一致。
范围：协议身份与元数据读写；无认证、真实调度、Provider或部署拓扑变更。

1. 固定2bd4af8探针，登记契约和旧版失败回归。
2. 修复Channel列表逐项授权，保留详情错误和合法空列表。
3. HTTP Workspace创建/授予/Agent/Channel/Session正反例，含幂等和拒绝不变。
4. 相关、全量、接口观察器验证；提交Evidence并交mymacclaude只读复审。
5. 部署等待HA-0056本机拓扑，随后必须本机→132；其余未观测入口仍单独推进。

检查点：旧3反例均按列表泄露断言失败；18项新增HTTP用例、相关44项通过，
完整verify为501 passed/16 skipped。148入口中136 observed且都有passing-test
2xx，12个尚未观测；不将其称为业务验收率。证据见HA-0059 acceptance。

8a7e840已获mymacclaude代码Approved；其他列表吞故障的既有Medium交HA-0060。
双部署仍待HA-0056本机拓扑选择，未执行。
