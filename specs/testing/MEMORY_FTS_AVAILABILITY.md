# Memory FTS可用性与故障边界（HA-0071）

测试入口tests/test_memory_fts_availability.py；仅临时SQLite、合成来源和TestClient。

1. 新库创建FTS精确缺模块时启动成功，readiness三字段一致且无路径；M1写入、
   去重、回放、supersede、retract、delete及失效旧键可用，缺失索引无SQL访问。
2. M1 Recall在Bank/状态/时间过滤后提供证据；M2 context返回503而非empty；
   按ID detail仍重新校验来源。所有GET/Recall/失败context不写入，不调用Provider。
3. 正常索引运行时故障：读不能吞锁/SQL错误降级；Retain/删除中途索引失败全库
   持久快照不变，移除注入后同key可重试。不得把索引故障写成成功收据。
4. 启动错误矩阵：创建时锁/只读/错误消息近似/错误码不符、重建的同名缺模块
   文本、已有坏view/普通表、canonical损坏、程序错误均传播并回滚本次重建。
5. 模块从不可用恢复：重启重建active canonical；清理的旧事实不再召回，其他Bank
   保留，收据无改动；第二次重启结果等价。ready只能在事务提交成功后发布。
6. 新测试放回固定基线，按行为断言失败；定向突变验证降级谓词、写入跳过、
   错误传播、重建和提交时序。记录定向/全量/verify及真实边界，不称线上验收。
7. 初始化出错后保持异常引用，验证已创建SQLite连接关闭、同DB租约可重新领取；
   不依赖GC释放文件锁。正常关闭与现有Workbench行为仍通过。

错误信封和runtime公开响应复用HA-0066/0069的三份Schema验证；不改响应字段。
索引影子表擦除、外部连接并发、真实无FTS5构建和性能均不在本项验收范围。
