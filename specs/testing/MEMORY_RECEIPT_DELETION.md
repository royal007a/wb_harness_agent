# Memory内容收据删除传播（HA-0070）

1. Retain首次与去重、Entity首次与去重、Relation首次与去重共六类收据均按
   canonical对象ID+Bank绑定；删除后response只含严格的失效标记。scope/key/digest
   不变；任何旧内容都不能借旧key重放。删除收据和无正文撤回收据继续回放。
2. Relation自身support Fact来自其他Source，但任一端点Entity被删时，同样删除
   Relation与其内容收据；未关联的实体、边、同Bank其他Source和其他Bank都不变。
3. 同请求旧key返回409 MEMORY_RECEIPT_UNAVAILABLE，异请求返回409 CONFLICT；
   两者total_changes=0且无内容泄漏。新key显式重建不复用旧source/entity ID，旧key
   仍失效。撤回或supersede未删canonical时的历史响应不受影响。
4. 故障注入覆盖清理之后、审计之后、删除收据写入之前；持久表快照相同，重试可
   成功。失效与canonical删除必须同一BEGIN IMMEDIATE，不能提前提交或开另一事务。
5. 旧库启动清理不需有本轮新表/依赖登记；旧内容响应对象仍有canonical时保留。
   只扫描确切的三类scope；无关产品收据即使包含相同文本或坏JSON也不读取。
   旧内容收据坏JSON/绑定错误和真实DB异常不吞；失败回滚整批清理。
6. 清理后重启、只读/旧key回放不得重建内容；回放自身也检查对象存在性。并发删除
   与同key回放在线性化点之前可返回原响应，之后只能409；不能复活或部分提交。
7. 失效标记源Schema拒绝正文/多字段/缺字段/假版本；实际409按公开错误信封验证。

验证全部使用临时SQLite、合成Source/Fact与TestClient；不代表物理擦除、多进程
或真实部署。测试入口`tests/test_memory_receipt_deletion.py`，另跑HA-0069与Memory
图/context/lineage、Workbench、全量及verify。更新HA-0069旧回放断言是ADR-0070
明确的兼容性变化，不能保留原bug测试作为成功标准。
