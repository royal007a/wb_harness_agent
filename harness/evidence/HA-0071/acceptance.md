# HA-0071 FTS可用性、故障传播与初始化清理

基线e8a3795（业务同4c17c47），候选待固定提交独立review与双部署。
规格specs/testing/MEMORY_FTS_AVAILABILITY.md、ADR-0071；不处理FTS影子词项擦除。

## 实际变更

- 只在无既有memory_fact_fts对象、CREATE精确报no such module: fts5且
  sqlite_errorcode=SQLITE_ERROR时，允许FTS5_UNAVAILABLE降级。不返回原始异常。
- 降级时Retain和生命周期不访问缺失投影；M1保持canonical关键词扫描，
  M2 context明确503，按ID详情仍校验来源。无模型/外部检索准入变化。
- 已有索引或其他创建/重建/查询故障不再被OperationalError宽捕获吞掉。
  MATCH探针在重建事务里验证真实索引，commit之后才发布readiness；失败回滚。
- 应用lifespan用ExitStack释放已构造的Service、Store和租约。初始化失败且
  异常traceback仍被引用时，连接关闭、同一DB可重新启动，不依赖GC。
  不承诺处理Store构造函数尚未返回时其内部半构造资源；本轮覆盖Memory初始化。

## 可复跑

```sh
.venv/bin/python -m pytest -q tests/test_memory_fts_availability.py
.venv/bin/python -m pytest -q tests/test_memory_fts_availability.py tests/test_memory_receipt_deletion.py tests/test_memory_write_contracts.py tests/test_memory_context.py tests/test_workbench.py
bash harness/verify.sh
```

最终31项测试SHA-256：c99925bf39d381122d335a416ee9b9e1bf5c673b98265d084c6c1cb2b0d39496。
在独立e8a3795 worktree只放该测试，保留所有基线helper/业务：28 failed、3 passed、
errors=0，1.73s。每项在行为断言失败，不用不存在符号/导入错误当反例。

| 文件 | 结果与边界 |
|---|---|
| before.xml/log | 初版24项：21 failed、3 passed；生产代码尚未修改 |
| before-final.xml/log | 最终31项在固定基线：28 failed、3 passed、errors=0 |
| new.xml/log | 初版24 passed |
| new-final.xml/log | 中间30 passed |
| startup-before.log | 补充启动资源清理反例，修复前1失败 |
| new-final-31.xml/log | 最终31 passed |
| targeted.xml/log | 15文件255 passed，25.41s |
| full.log | 1328 passed、16 skipped，154.67s；skip不算通过 |
| mutation-control.log | 隔离候选worktree 31 passed，1.80s |
| mutation-plan/results.json | 14/14指定突变被杀死，errors=0，逐次恢复cmp |
| mutation-harness-indent-error.xml/log | 首次脚手架未保留缩进导致收集错误；修复脚手架重跑，不计有效突变 |

相关15文件包括新测试、HA70、HA69、Memory plane/context/context evaluation/graph/
graph evaluation/entity catalog/fact lineage/temporal/semantic、HA66读取、OpenAPI、
Workbench。observer显式通过-p harness.pytest_interface_evidence启用；targeted观察
74入口，full观察148；这些不是功能验收率。两份记录的146个源码/Schema/测试/
映射SHA运行内稳定，事后逐文件核对无漂移；git字段为e8a3795+dirty候选，不倒填。

14个突变覆盖：无索引仍写/删、忽略既有对象、错误文本/错误码判断、跳过重建、
跳过MATCH验证、索引包含inactive、提前ready、返回原始错误、吞查询异常、提前
提交、泄漏连接、泄漏租约。提前提交seed成功，失败在持久快照比较；total_changes
会计入回滚写，所以失败原子性比较持久行。14/14不是全库mutation score。

## not_evidence

- SQLite连接真实，缺模块通过仅拦CREATE的Connection子类注入；没有构建真实
  无FTS5版SQLite。真实DROP投影和同名view/普通表则确实在临时DB执行。
- 单进程TestClient、临时DB、合成Source/Fact；重启为关闭客户端后新app；没有
  网络socket、正式DB、Provider、Keychain、真实用户数据或部署证据。
- 初始无投影时的M1扫描和正常FTS候选不承诺完全等价/大库延迟；context不降级。
- ready仅代表最近初始化成功；运行中丢索引报错，不自动修复或更新状态快照。
- Memory启动收据清理是HA70独立事务；后续FTS重建失败不会撤销前一事务的已
  提交清理。发布必须备份；不称整个app初始化为一个事务。
- 不清FTS影子表历史词项/WAL/备份，不把失败闭合当隐私擦除。图错误响应声明、
  22个空成功JSON接口及其他历史Low仍未在本项修复。
- 双部署仍需HA56兼容本机拓扑，不能跳过8765直接更新132；所有门禁未开。

统一verify、提交和review状态在收口记录追加，不拿定向/全量代替实际发布。

## 收口

`bash harness/verify.sh`退出0：1328 passed/16 skipped，145.24s；检索2、Agentic2、
adaptive6和各Memory/Team离线评测、准入检查、JS语法、接口清单与diff检查通过。
已完成log/XML只机械清理行尾空白，XML参数化名称用哈希缩写，两个观察JSON压为
单行；结果和源码摘要不变。两处自建worktree恢复核对后清理，原始基线与突变
证据保留。待固定提交独立review；正式8765/132与真实SQLite无FTS构建未验收。
