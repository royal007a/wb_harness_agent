# HA-0070 内容收据删除传播

基线1c9aaf5；固定4c17c47独立Approved，待双部署。ADR-0070定义了对
HA-0069历史回放语义的明确变更，不把既有bug测试保持绿色当作兼容要求。

## 实现及边界

- 删除Source后的Retain/Entity/Relation内容收据response替换为严格无正文标记，
  scope/key/digest保留。间接依赖（Relation支持Fact仍在，但端点Entity已删）
  同样删除并失效；canonical存在性用对象ID+Bank核对，不扫描正文关键词。
- 同key同请求409 MEMORY_RECEIPT_UNAVAILABLE；异请求先409 CONFLICT；均零写。
  不能删除幂等记录重执行业务。用户换新key显式重建可创建新对象，但旧key仍无效。
- 启动时同事务清理三类旧孤儿内容收据；回放在读收据的同一事务内再次查canonical，
  只拒绝不做lazy清理。DELETE只清当前Bank；其他Bank只由各自删除或启动清理处理。
- 错JSON/绑定返回固定500 MEMORY_RECEIPT_CORRUPT；DB异常仍传播；故障全批回滚。
  撤回/supersede/过期仍有canonical时历史内容收据不变，删除/撤回的元数据回执不变。

## 可重跑命令

```sh
.venv/bin/python -m pytest -q tests/test_memory_receipt_deletion.py
.venv/bin/python -m pytest -q tests/test_memory_receipt_deletion.py tests/test_memory_write_contracts.py tests/test_memory_graph.py tests/test_workbench.py
bash harness/verify.sh
```

最终新测试SHA-256：`ffb48dfe4c17338a19d6057d74a87c021c28e546dc6d2c8d0fedd821885300f3`。
基线：把**只有此新文件**放回1c9aaf5，保留旧helper/业务/Schema，使用
`-k 'not marker_contract_is_strict'`，得到23 failed、5 passed、4 deselected、errors=0。
四个新标记Schema用例不属于旧业务反例，明确排除。失败均在行为断言，不是导入错误。

|证据|结果与口径|
|---|---|
|before-initial.xml/log|早期28项，19 failed/9 passed；当时已加标记Schema，不是完整固定基线|
|before-final.xml/log|中间31项回1c9aaf5，22 failed/5 passed/4 deselected|
|before-final-32.xml/log|最终32项回1c9aaf5，23 failed/5 passed/4 deselected，2.31s|
|new-initial.xml/log|早期新28+既有40共68 passed|
|new.xml/log|中间31项passed|
|new-final.xml/log|最终32 passed，2.57s|
|targeted-invocation-error.log|遗漏显式observer插件，exit4；不是测试失败/验收证据|
|targeted.xml/log|中间14文件223 passed，29.00s|
|targeted-final.xml/log|最终14文件224 passed，24.44s|
|full.log|1297 passed/16 skipped，141.74s；跳过不计通过|
|mutation-control-final.log|隔离worktree候选32 passed，2.26s|
|mutation-*.xml/log|12/12指定突变被杀死，errors=0；逐次恢复并cmp|

相关14文件为新测试、HA69、memory plane/context/context evaluation/graph/graph
evaluation/entity catalog/fact lineage/temporal read/semantic admission、HA66、
OpenAPI和Workbench。观察插件命令额外带`-p harness.pytest_interface_evidence`。
最终targeted观察74入口（72有passing-test 2xx），full148（148有passing-test 2xx）；
入口观察不是功能验收率。145份源码/合同/测试/映射哈希运行中稳定，事后无漂移。
观察器记录1c9aaf5+dirty候选，不倒填之后的提交SHA。

12突变细节见mutation-plan/results.json。提前提交在seed成功后的持久表快照
断言失败；拆分回放事务被SQL trace边界断言杀死。保留digest、间接图依赖、
启动清理、Bank绑定/隔离、回放存在性、标记拒绝正文各有针对性反例。12/12只
指这些定向突变，不是全库mutation score。两个临时worktree还原后清理，证据保留。

## not_evidence

- 只用临时SQLite、TestClient、合成Source/Fact；并发为单Store RLock下两个线程，
  新app同DB为进程内重启模拟。没有多进程、真实socket、真实Provider或生产数据。
- 清理response不可逆；代码回退不恢复旧内容。发布前必须备份实际DB；没有修改
  正式DB，也没有演练真实旧库升级/备份恢复。已有数据库启动会执行这项逻辑迁移。
- 不清理WAL/空闲页/备份/用户端副本、独立来源、其他产品产物；FTS5影子表词项
  也可能残留，不承诺其擦除。scope/key/digest和Bank标签/审计元数据保留；不是
  隐私抹除证明。详见review.md。canonical被手工损坏而失踪也会
  使内容收据不可用，不把UNAVAILABLE当成已证明正常删除。
- 清理扫描在本机小规模数据上测试，未做大量历史收据性能/启动延迟验收。损坏的
  受管收据可阻止启动/当前Bank删除，保持fail-closed，不静默跳过。
- HA-0069复审的重复撤回audit负例、FTS不可用时Retain写入退化、剩余22个空JSON
  成功声明均未在本项修复。双部署仍待HA-0056兼容本机拓扑，不能直接跳到132。

最终verify及提交/review状态见后续收口记录，不以本地测试代替部署。

## 收口

`bash harness/verify.sh`退出0；全量1297 passed/16 skipped，检索/Agentic/adaptive、
Memory/Team确定性评测、准入状态、JS语法、接口清单和diff检查均通过。
已完成log/XML仅机械清理行尾空白，XML参数化testcase名改为摘要，观察JSON压为
单行；不改变测试结果和源哈希。两个临时worktree已删除，根工作树实现将固定提交
交独立review。HA-0069独立Approved另已登记；本项仍无双部署/真实模型证据。

后续独立复审4c17c47 Approved；32项和旧23反例重跑，旧库升级与额外故障探针
通过。2 Low（FTS影子词项残留、图写入错误声明）及1 Info见review.md。
