# Memory图写入HTTP合同（HA-0072）

测试入口tests/test_memory_graph_write_contracts.py；两入口/entities和/relations。

1. 真实新建、业务去重、同key回放均201；三套Schema（源/静态/动态）一致，
   success拒绝空对象/未知字段/缺字段，dedup与audit分支一一对应。无Source正文。
2. 实际404/409/415/422/500复用local_http_error；动态422不能仍是FastAPI空占位；
   请求体严格，幂等key1..128，129拒绝；静态/动态与实际行为对应。
3. 新key仅接受同Bank、当前有效的Fact/Source/端点：未来Source、过期Source、
   future/inactive Fact以及无效端点拒绝，不写收据；拒绝后恢复条件可同key重试。
4. 规范表写入后audit/收据故障全事务回滚，错误响应不含注入的秘密标记；去掉
   故障后同key可成功。失败原子性比持久行，不误用total_changes计数回滚。
5. 旧key是历史收据，retract/supersede后可原样读；delete后409且不写入，
   重启后相同。不同Bank相同内容/名称不能串用支撑引用；其他Bank不受删除影响。
6. 固定基线保留原helper运行新测试；定向突变分别锁定错误绑定、分支、header、
   时间检查和事务回滚。只记录实际运行数字，不能用schema数量代替功能验收。

非目标：完整图读取契约、FTS影子词项擦除、外部Provider/认证/自动抽取、生产图
评估、物理隐私擦除、大库性能、多连接并发。双部署仍有本机拓扑阻塞。
