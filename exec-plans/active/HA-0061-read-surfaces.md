# HA-0061 剩余只读接口行为验证

1. 对照现有实现和ADR，写明11入口的读取内容、生命周期、拒绝和非证据边界。
2. 临时DB通过公共HTTP创建数据，验证空/非空、详情一致、隔离、持久性、HEAD。
3. native列表只用测试准入档案创建元数据，stream哨兵及门禁拒绝保持零外发。
4. 重跑相关、全量观察器和verify；记录公开Schema缺口及实测问题。
5. 固定提交交mymacclaude只读复审。不改部署；整体发布仍等待本机拓扑后本机→132。

2026-10-04检查点：1–4完成。新增57项，相关123 passed，全量632 passed/16 skipped，
verify exit0；148/148入口均有passing-test 2xx。已记录公开Schema与复审Low的
未实现边界；业务代码/正式服务未改。证据：harness/evidence/HA-0061/acceptance.md。
当前waiting_approval，不将测试补齐等同于12小时目标或双部署完成。
