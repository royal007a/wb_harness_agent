# HA-0069 Memory写入生命周期

基线697ef73；不碰正式DB、8765、132、Provider或凭据。

1. 合成Source/Fact与临时SQLite复现损坏档案、DELETE分块请求体。
2. 先补源Schema、静态/动态绑定，再实现窄失败边界修复。
3. Retain新写/内容去重/纠错、撤回/重复撤回、删除/回放；同事务故障回滚。
4. 正反例、基线测试、突变、Workbench/全量/verify；固定提交交独立review。

删除只涉及现有canonical与派生索引；幂等历史收据仍可能含Fact statement，
不称为全库抹除。另登记删除传播缺口，不能以HTTP契约掩盖它。

收口：新增40、相关192通过；旧版35 failed/5 passed/errors0；10/10有效突变。
全量1265 passed/16 skipped，verify退出0，144份源码哈希稳定。等待固定提交
独立review及兼容本机拓扑明确后先8765再132发布。证据HA-0069/acceptance.md。
