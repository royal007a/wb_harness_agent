# HA-0066 Memory / Research读取契约

1. 记录7项响应及实际边界；旧文档反例。
2. 源Schema、静态与动态绑定，实际HTTP空/非空/生命周期实例校验。
3. Memory退化状态、研究门禁历史、嵌套负例、无外发/无写入及定向突变。
4. 冻结测试回基线；定向、全量、verify及证据哈希，固定提交交独立review。
5. 双部署待HA-0056兼容本机拓扑，禁止跳过本机。

检查点：新增36、相关283通过，旧36项公开合同反例失败，8/8定向突变被杀死；
全量1131 passed/16 skipped，verify exit0。141项观察器源哈希稳定。证据在
harness/evidence/HA-0066/acceptance.md；5429c62独立Approved，Low/Info已登记，
等待兼容本机拓扑后的双部署。
