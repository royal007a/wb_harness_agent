# Pi Product Run HTTP 与终态（HA-0068）

范围：`/api/local/pi-contract-review` GET/POST、`/{run_id}` GET、
`/{run_id}/events` GET、`/{run_id}:gate` POST。与HA-0067的无Run管线分离。

1. 创建202返回Task/initial_run；列表只列本引擎根Run；详情返回Run、Task、
   Artifact元数据、离线mode/runtime_enabled=false/external_calls=0以及最新Gate。
   计数是离线能力声明，不是全系统调用遥测。
2. 事件JSON分页每页至多500条，after_seq范围0..9223372036854775807。
   next_seq是本页末条sequence，空页原样返回after_seq，不能用Run最新序号跳页。
   HTTP沿用FastAPI整数转换；Store及服务直接调用拒绝bool/float/字符串/越界。
3. 详情最新Gate必须从全部事件而非第一页选取；GET不执行Run、解析凭据或写库。
   详情在同一只读锁窗口取Run/Gate/Artifact，不把多个时刻拼成不一致快照。
4. Gate pass→succeeded/GATE_PASSED，reject→failed/GATE_REJECTED。
   首次决策的引擎/当前waiting_approval检查、Artifact/Event、终态、幂等收据
   同事务。取消/另一次决策先完成时，后来的新key返回409，不覆盖终态。
   相同key+body返回原收据且零写入；不同body为409 CONFLICT。历史收据不等于
   当前执行许可。不新增principal/租户边界，仍是可信本机操作。
5. 执行结果提交前，在同一事务内再查取消/超时；终态不得被迟到结果改回
   waiting_approval，也不得新增产物/候选事件。迟到Adapter事件同样拒绝。
   这不宣称同步sidecar能被立即杀掉或取消网络计费。
6. 请求和Gate body严格拒绝额外字段，key 1..128；默认与422错误同local_http_error。
   源合同复用core Task/Run/Event/Artifact，静态与动态均引用，不复制三份业务模型。
   Schema约束形状，事件与资源/Artifact引用完整性、游标算术由行为测试保证。
7. 模拟生命周期必须覆盖queued、running、waiting_approval、pass/reject、cancel、
   failure、重启和重放；人工Gate记录可下载且哈希匹配。合成Adapter只验证控制面，
   既有Faux sidecar测试单独运行，不证明PDF语义、法律质量或真实Provider接入。

本项不修改通用rerun次数、PDF解析准入或通用HTTP认证。源Schema不是运行时响应
拦截器；不把API观测数当全部功能验收率。实际双部署须另行满足HA-0056前提。
