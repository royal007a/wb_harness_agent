# 已登记只读入口补验（HA-0061）

基线fff8d75。范围是尚未观测的11个方法/路径，非所有功能验收声明。
HTTP通过临时SQLite、run_worker=False验证；不启动真实Provider、CLI或容器。

| 入口 | 行为断言 |
|---|---|
| GET memory/banks | 空/非空、倒序、固定local所有权、幂等不重复、与详情bank一致、无Source/Fact正文、重启持久 |
| GET research / research-agents / research-native | 只返回本引擎根Run、排除Child和其他引擎；倒序、幂等、取消/完成状态与详情一致 |
| GET sample | CSV字节与版本化样本一致、正确下载头、可上传解析；读取本身不登记资源 |
| GET health | 只证明本进程的静态存活响应；不得当作Provider、release/PID或容器就绪 |
| GET resources / resources/{id} | 空/非空、倒序、去重、CSV/PDF登记元数据与上传/详情一致，无原始内容；不存在404/NOT_FOUND；重启持久 |
| GET runs/{id}/replans | 无候选时空列表、不存在Run为404；源Run隔离；当前proposed/awaiting_confirmation/cancelled/confirmed状态，取消重提倒序、不触发执行 |
| HEAD openapi.json / static/{path} | 与GET状态及类型/长度一致、正文为空；静态缺文件/越界拒绝；不改持久数据 |

所有入口仍走现有Host/Origin/代理前缀边界。研究native非空列表只能来自临时测试
准入档案创建的元数据，禁止真的执行SDK。测试应以哨兵保证没有进入native stream；
关闭测试门禁后仍可读取历史，这不代表新Run获准执行。

现有Schema可用时校验实际实例及负例；公开响应Schema占位或缺失时单列缺口，
不得以本轮字段断言替代公开机器契约。当前确认 health/resources、Memory Bank
列表及三类research列表需要后续补公开响应声明；资源本地元数据也不能硬套
目标架构中尚未落地的Resource对象。

本轮不扩大运行权限、不创建鉴权、不改变业务行为。若探针发现真实缺陷，先登记
反例与契约，再修复；即使11个入口均观察到，也不等于148个入口/全部分支验收。
