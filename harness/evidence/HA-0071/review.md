# HA-0071 独立复审

mymacclaude对7a03b99给出Approved，3 Low及1条信息。来源消息
om_x100b632e2d7340a0c2c622e6a0c61c9。以下是复审者报告，不冒充作者重新执行。

- 指定5文件165 passed；新测试SHA一致，原样回e8a3795为28行为失败/3通过/errors0。
- 真实SQLite 3.53.4锁、只读、已有FTS损坏均传播；坏索引连续重启规范表与影子表
  不变。近似缺模块文本被拒；退化生命周期、运行时DROP、重启重建均符合边界。
- COMMIT失败不提前ready；保留traceback且关闭GC时，Memory初始化、收据清理、
  runtime recover失败后连接/租约都释放，worker启动后失败也join；可立即重试。
- 独立10突变杀死9个。未复跑255/1328/verify或作者提前commit突变；没有真实
  不含FTS5的构建、正式DB、Provider或部署证据。

## 后续问题（不阻塞代码批准）

1. 测试缺少大写`no such module: FTS5`，lower化比较突变存活；生产仍精确比较。
2. 手工把投影换成同名同列fts4，重建和MATCH可以成功，但runtime仍标sqlite-fts5@1。
   当前不验证sqlite_master.sql中的引擎身份；不是已实现的实时完整性监测。
3. 运行时替换为同名普通表，retain/delete可成功，读或重启才失败；canonical正确，
   readiness仍是上次初始化快照。不能宣称运行时任意投影损坏都由写路径检测。
4. 主表缺失且缺模块时，孤立影子表可以保留，仍属MEMORY-FTS-02未解决范围。

Store构造尚未返回的半构造资源、大Bank降级扫描延迟未验收。双部署仍受兼容
本机拓扑阻塞；本次Approved仅代表固定提交代码与上述离线证据。
