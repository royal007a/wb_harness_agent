# ADR-0071：限定FTS缺模块降级，不掩盖数据库故障

状态：本地实现与验证通过，待独立review与双部署；HA-0071，基线e8a3795（业务同4c17c47）。

MEMORY-FTS-01：初始化捕获所有OperationalError，却在Retain无条件写FTS；
模块缺失时M1仍500。查询也吞OperationalError，可能把锁/坏SQL伪装成正常召回。

## 决策

1. 唯一允许的启动降级：库里没有memory_fact_fts对象，创建FTS5时得到SQLite的
   `no such module: fts5`（SQLITE_ERROR）。状态为ready=false、engine=null、
   error=FTS5_UNAVAILABLE；不存原始SQL异常文本。创建语句以外的错误不走此分支。
2. 此状态下Retain/supersede/retract/delete只写canonical及既有图/收据/审计，
   不访问缺失索引；事务和旧键规则不变。M1 Recall沿用显式的canonical关键词
   扫描；M2-A context仍503 MEMORY_INDEX_UNAVAILABLE，不能冒充空历史。
3. 已有索引但模块不能读取、同名view/普通表、锁/只读/损坏/SQL错误、索引重建
   或查询故障不属于模块缺失降级：启动失败或请求500（通用无密信封），不自动
   切模式、不提交半个写入。只把创建语句的精确错误作为能力判定，禁止宽catch。
4. 正常启动在同事务创建/重建并执行一次MATCH读取；提交之后才发布ready=true。
   readiness表示最近初始化成功，不是实时存储健康探针。运行中索引丢失或故障
   请求失败，需显式重启/修复；不在GET或失败写入里重建，也不自动提高权限。
5. 恢复带FTS5的环境后，重启从active Source/Fact重建；不复制撤回/supersede/已
   删除记录。无新API、依赖或模型/semantic权限；现有响应Schema保持兼容。
6. 初始化失败要释放已构造Store和文件租约，即使调用方仍持有异常traceback；
   修复错误后的同进程启动可重试，不能留下假“数据库已占用”。清理后仍重抛原错。

## 边界

降级查询和FTS查询候选集/性能不承诺等价；canonical扫描不是语义检索。
不能访问已有索引时拒绝启动，是为避免跳过删除而留下可查询的旧数据。
FTS影子表历史词项擦除另列MEMORY-FTS-02；本项不修复其隐私残留，不做在线重建、
全库损坏检测、正式数据迁移或超大Bank性能承诺。测试模拟缺模块，真实SQLite
无FTS构建需另行验证。双部署继续先本机再132，拓扑阻塞不绕过。
