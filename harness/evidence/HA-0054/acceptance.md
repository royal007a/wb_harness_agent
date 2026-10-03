# HA-0054 验证（进行中）

基于 HA-0053 合成探针确认 Runtime 取消与重复执行缺陷。本项规格已登记；
默认真实模型门禁保持关闭。下面按阶段记录结果，不把中间通过当作发布完成。

## 反证与修复

- `before.xml`：未修改实现时，新增生命周期用例 13 failed、2 passed。
  失败分别暴露取消覆写、重复执行、Session 并发、取消清理、等待超时、失败
  重放计数归零、超长错误码及启动恢复缺失；没有真实网络。
- `after.xml`：首版修复后原 15 项 + 既有 Runtime 3 项，18 passed。
- `targeted.xml`：补充启动保留终态、凭证解析过程中取消、稳定的 ASGI 断线
  场景后，Runtime/Lifecycle/Workbench 共 76 passed。
- 实现使用数据库事务领取，不依赖单个 Runtime 实例的内存锁；重复消费者
  没有取消权。所有终态均保留，取消/失败无 assistant 发布。
- `verify.log`：完整 verify exit 0，325 passed、16 skipped；其后确定性
  评测、两类外发准入拒绝检查、JS 语法与 diff 检查通过。
- 双端发布和独立 review 仍待完成。

## 真实沙箱回归的测试预算问题

首次实际容器测试 15 passed、2 failed，保留 `local-sandbox.xml`，不覆盖。
输出超限/输入只读两例先被 2 秒 start+attach+执行超时终止。独立计时探针
复现 2 秒 TIMEOUT，而生产默认 10 秒预算可分别触达 OUTPUT_LIMIT 和
EXECUTION_FAILED；详见 sandbox-deadline-diagnosis.json。
仅更正测试：timeout 专项仍为 2 秒，其他规则专项用现有默认 10 秒且仍要求
精确错误码与容器/输入目录清理。未修改生产沙箱预算或接受任意失败充当通过。
修正后 `local-sandbox-after.xml`：17 passed，真实本机 Colima 容器。
全量 verify 的容器专项按原设计 skip；单独这次 opt-in 运行才是容器证据。
