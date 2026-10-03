# HA-0065 Product边界与契约负例

1. 明确int64游标与引用格式，登记规格、ADR、Work Item。
2. TestClient实际实例先跑基线反例；修复入口/Store与源/静态/动态契约。
3. 422信封、required、const、UTC的精确负例和突变验证。
4. 最终测试放回基线；相关/全量/verify、源哈希、固定提交独立review。
5. 实际发布受HA-0056本机拓扑约束；先本机再132，不改门禁。

检查点（2026-10-04）：新增60、相关250通过；最终测试回到0ee58a0产生28项行为
失败；10个定向突变全部被杀死。全量1095 passed/16 skipped，verify exit 0。
证据：harness/evidence/HA-0065/acceptance.md。实现和离线验证已完成，等待固定
提交独立review；双部署另待兼容本机拓扑确认，尚未完成，不越过本机发布132。
