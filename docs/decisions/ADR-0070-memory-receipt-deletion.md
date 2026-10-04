# ADR-0070：删除优先于内容收据的历史回放

状态：4c17c47独立Approved，待双部署；HA-0070，基线1c9aaf5。

HA-0069明确发现：删除Source及其Fact/Entity/Relation/FTS之后，旧Retain和图写入
收据仍保留派生文本。直接删除幂等记录会让同key重试重新执行业务，不能采用。

## 决策与兼容性

1. 限定三类内容收据：`memory:retain:{bank}`中的source、
   `memory:entities:{bank}`中的entity、`memory:relations:{bank}`中的relation。
   对象必须仍存在于该Bank的canonical表，才能继续回放历史成功响应。
   判断使用类型化的对象ID与Bank绑定，不搜索文本，不跨产品scope。
2. 删除在同一个BEGIN IMMEDIATE内先移除canonical及图派生，再把同Bank中
   对象已不存在的内容收据response替换为`memory-receipt-tombstone@1`常量。
   保留scope/key/request digest，标记不保存对象正文、旧响应或请求。
   审计只增加失效数量；故障时整个删除回滚。
3. 同key同请求命中失效标记返回409 `MEMORY_RECEIPT_UNAVAILABLE`，不写入、不
   重新执行；异请求先返回原有409 CONFLICT。删除/撤回的无内容收据继续原样回放。
   新key显式重新提交同内容仍可创建新Source；这不是对所有未来输入的内容封禁。
4. 启动时在独立原子事务中扫描三类旧内容收据，以同一canonical存在性规则清理
   历史孤儿。这是不可逆的逻辑payload清理，不是普通GET的副作用；重复启动不
   重写已清理标记。发布前备份真实DB，代码回退不会恢复被移除的旧收据内容。
5. 回放还要在读取收据的同一事务里再次查canonical，防止启动后残留孤儿被回显；
   这道检查只拒绝，不写清理。损坏JSON、错Bank绑定或DB/程序异常不得当成成功
   或空结果；清理事务失败应回滚，不吞异常。

“不存在”也包括手工破坏canonical造成的孤儿，本切片不证明其一定由DELETE产生，
所以错误叫UNAVAILABLE而非DELETED；不提供全库损坏检测。撤回/过期/supersede
仍有canonical行，因此不在本次内容清理条件内，历史收据语义保留。

## 非目标

不清理磁盘空闲页/WAL、备份、客户端副本、其他产品产物或独立来源的相同文本；
FTS5影子表可能仍保留已删词项（不是空闲页），本轮也不保证其擦除；
scope/key/digest、Bank标签、审计元数据继续保留。不做FTS不可用时的写入恢复，
不加身份/模型/外部检索权限。验收见`specs/testing/MEMORY_RECEIPT_DELETION.md`。
