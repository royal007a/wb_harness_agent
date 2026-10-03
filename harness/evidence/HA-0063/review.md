# HA-0063 独立复审

2026-10-04，mymacclaude对固定116a164给出Approved，附2个Low。
来源：飞书本话题消息om_x100b6323700f30a0c467f34f3a94e75。
以下是reviewer报告的独立结果，不冒充本轮作者重新执行的探针。

- 新64、相关182通过，测试SHA与acceptance一致；旧7ac1498上最终18项均HTTP行为失败。
- 五类对象各13–16种损坏，经13读取入口：实际读到的坏行返回500，未发现跨域。
- 非调用者目录记录、合法inactive、惰性过期回滚、固定500信封均通过。
- 16处突变杀死15处；worktree与临时DB清理，主仓库HA-0064改动为作者自己的工作。

## 未阻塞的限制

1. L1：Channel archived与其membership损坏同时存在时，Channel列表会先读并
   校验membership而返回500；详情先判archived返回409，其他列表可隐藏该对象，
   根本没读到membership。删除Channel列表的提前校验仍能通过182项测试，缺专门
   反例。Workspace archived的同类短路仅为reviewer读代码推断。不能声称所有关联
   记录在任何访问决定之前均被校验；后续补组合状态回归，当前不提权或泄露。
2. L2：仅将Channel的SQL workspace_id改到另一scope，旧scope的列表因JOIN选不到
   该行而返回空，详情才发现列/JSON不一致并报500。规格补充该明确边界；不是全库扫描。

边界：临时SQLite和TestClient；完整损坏写接口矩阵、并发回滚、日期format、正式
数据及双端部署不在此次批准范围内。TEAM-REPLAY-01仍是独立HA-0064任务。
