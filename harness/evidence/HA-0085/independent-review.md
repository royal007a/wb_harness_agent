# HA-0085 独立复审回执

2026-10-07收到mymacclaude的可读飞书消息：**Approved**。批准对象为fd0b323；1ae1a6a只修改证据XML空白，已另用git diff核对未改运行代码。

复审方报告在自己的临时worktree独立运行`test_dsh_crossing_retirement`和`test_dsh_crossings`，31项通过，并增加两个探针：

1. 正常成功的付款Run，最终事件为run.succeeded；此前调用事件没有failed，未使用票据为retired。
2. SDK本地拒绝错误类型的工具参数，两张票据先retired，随后run.failed；错误码仍是DSH_CROSSING_PREDECESSOR_PENDING。

复审方另核对了成功发布事务、失败退役事务、finally仅处理持久终态、取消后允许追加结算审计、历史failed不重写及dsh-crossing@2区分。

以上是独立复审方报告的运行结果，本文件没有将其描述为本轮作者再次复跑，也没有附上尚未收到的独立原始日志。作者原有反例、突变与失败运行仍完整保留在acceptance及相邻证据文件中。

## 保留边界

- DSH-CROSSING-01（SDK本地拒绝后的错误码不够准确）仍未修，不阻塞本切片。
- 当前前端未展示调用事件；以后增加展示时应区分retired和unknown，不把两者都显示为调用失败。
- 取消后可能追加unknown结算事件；不承诺所有终态必为最后事件。
- 批准仅限固定切片的代码和离线验证，不包括本轮完整门禁、真实Provider和部署。
- 完整验证尚未通过，8876未切换；任务包含部署验收，因此仍保留waiting_approval，不提前标记完成。
