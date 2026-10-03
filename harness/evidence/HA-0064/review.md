# HA-0064 独立复审

2026-10-04，mymacclaude对固定0ee58a0给出Approved，附2个Low和1个Info。
以下为reviewer独立回报，不冒充作者本轮再次运行了这些探针。只读worktree、
临时SQLite、TestClient；主仓库HA-0065的14处修改为作者的下一原子任务。

- 程序枚举team/recovery恰好25个POST；29处必填replay_authorize对应25入口+4包装。
- 新287通过，相关9文件469通过（作者526另外包含57项Workbench，不矛盾）。
- 128项额外对抗：全部25入口重启后回放、过期lease/deadline、暂停后恢复权限，
  都不重执行业务且DB快照/total_changes不变；底层访问故障不泄露收据。
- 25入口改actor复用key都409；旧116a164恰好25行为失败，测试SHA一致。
- 13个突变，捕获跳过重查、digest次序、动作重执/回滚、吞故障、去掉binding/
  reviewer/owner/Recovery role等；下面2条是不受现有测试保护的存活突变。

## Low / Info

1. channel_grant因不需要Channel membership而被CHANNEL_READERS整体排除，
   也漏了独立的归档反例。生产代码会正确409；将回放的_channel改为不查status
   的_row，官方287仍过，reviewer新增探针才能抓到。后续补这条专用反例。
2. 同一事务条款没有测试锁定：改成读缓存与授权分属两个事务，现有测试仍过。
   当前代码实际用同一BEGIN IMMEDIATE；不把串行零写入证据当成并发线性化证明。
3. Info：部分grant/agent binding只是收据对原path/body，正常缓存下恒真，不能
   用来宣称发现任意归属漂移。规格已限制缺历史上游快照的保证，不是新缺陷。

边界：主体主要为local_admin，未完整验证非管理员回放、并发撤销线性化、嵌套
引用或缓存篡改；全量1035未由reviewer重跑。同scope改body可探测key是否存在
是既有409行为，不回收据。真实双部署仍未验收。
