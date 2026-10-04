# Memory写入HTTP与失败边界（HA-0069）

|入口|成功|源定义|
|---|---|---|
|POST /api/local/memory/banks/{bank_id}/retain|201|local_http_memory_retained|
|POST /api/local/memory/sources/{source_id}:retract|200|local_http_memory_retracted|
|DELETE /api/local/memory/sources/{source_id}|200|local_http_memory_deleted|

1. 请求沿用retain_request、空JSON撤回、无body删除；key必填1–128字符。
   DELETE无Content-Length或分块传输同样不得包含非空body。
2. 响应源、静态、动态三套Schema拒绝空对象、多字段、坏ID/时间/计数。
   Retain首次写入1–16 Fact且有audit；内容去重facts=[]、audit=null。
   重复撤回already_retracted=true且count=0，没有伪造新的audit或图计数。
3. canonical Source content及Fact detail不出现在写回执；statement本身是交付。
   同key同规范化请求为历史回执，不承诺反映后续supersede/retract状态；HA-0070
   改为删除后旧Retain/Entity/Relation内容收据返回409，不再返回正文。
   异请求同key409；合法回放业务状态和total_changes均不变。
4. 来源、Fact、FTS、图派生、审计与幂等收据在同一事务；故障返回错误且可见
   DB快照不变。SQLite total_changes包含已回滚尝试，不能拿它证明失败没有尝试写。
5. 删除清除本来源canonical及相关图/索引；不自动复活被supersede的旧Fact。
   HA-0070把相关Retain/Entity/Relation内容收据一并失效；仅保留scope/key/digest
   和无内容标记。历史删除/撤回收据不变；物理磁盘/WAL/备份仍不在范围内。
6. 损坏准入档案fail-closed且不影响状态读取；输出类型码不含文件内容。
   负例锁定counts.sources、external_calls非负及FTS不可用时error为string。
7. 合成Source/Fact、临时DB、TestClient与直接故障注入；不代表真实socket分块
   完整协议、用户身份隔离、Provider、线上检索或正式部署。

测试：tests/test_memory_write_contracts.py。先按基线实例失败，再修复并做定向
突变；现有memory生命周期/graph/context/semantic/Workbench必须回归。
