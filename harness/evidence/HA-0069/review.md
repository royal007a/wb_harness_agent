# HA-0069 独立复审

mymacclaude对697ef73..3d83bd5给出Approved（2 Low、2条说明）。消息来源：
om_x100b632dc091a0a0c3ef44c01376717。以下为复审者报告，不冒充作者重复执行。

- 指定5文件165通过（作者192为13文件），原40项回697ef73为35失败/5通过/errors0。
- 档案异常覆盖缺失/目录/BOM/null/NaN/非UTF8/超深/超长整数/NUL路径/权限等，
  fail-closed且无PRIVATE/路径；注入RuntimeError/OperationalError/TypeError/
  KeyError/MemoryError仍抛出。文件无字节上限，不据50MB测试宣称抗DoS。
- 真实uvicorn0.49/h11、随机loopback原始socket验证DELETE：合法空body及空
  chunked成功；非空chunked/CL非零/Expect等拒绝且整库不变。未装httptools，
  反向代理与多进程未测。
- 三套Schema在16 Fact、supersede、含图撤回、零active Fact撤回、Public、删除
  已撤回Source等路径一致；第2次索引写入失败整库回滚，同key重试成功。
- 11独立突变杀死10个；提前提交的反例seed成功，失败确实在持久快照比较。

Low与说明：

1. 重复撤回分支的audit_id禁止项缺独立负例；应使用already_retracted=true、
   count=0同时加入audit_id，避免count=1先挡住。生产Schema当前正确。
2. false_zero仅是ASGI层CL与流不一致；真实HTTP/1.1 CL:0后额外字节不是本次
   请求body，h11正常返回200并删除。不能把该TestClient测试说成网络字节拦截。
3. ValueError捕获也含校验器内部同类型编程错误，方向fail-closed；不称所有程序
   错误必然传播。CL:00拒绝较保守；Expect+CL:0先100无害。

全量1265/verify未独立重跑；门禁未开，正式双部署仍未验收。HEAD1c9aaf5是作者
登记HA-0068 review的文档提交，不是复审者改仓库。Memory收据删除后续在HA-0070。
