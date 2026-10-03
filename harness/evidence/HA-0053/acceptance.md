# HA-0053 证据（进行中）

初始版本 b51dce6；本机及 132 loopback health 均为 ok，132 git HEAD 87934de。
本次现有 `bash harness/verify.sh` 在 pytest 阶段失败：302 passed、16 skipped、
1 failed，耗时 60.30s。未执行其后的评测/JS 检查，不能称为全量通过。

失败：`tests/test_workbench.py::test_checkpoint_restore_rejects_arguments_and_survives_restart`，
`fail_after_checkpoint` 期望 failed 但观察到 running。该用例启动真实 Worker 后
又在测试线程手动执行同一 Run，需要固定故障注入时序，而非增加 sleep。

审查交接已发 mymacclaude（基线 b51dce6），尚未收到本阶段批准。
接口/功能矩阵、补充验证、运行时修复与双端迭代仍在进行。

## 修复与新鲜基线

- 新建 `specs/testing/README.md`、人工功能表及自动生成接口表：148 个方法/路径
  组合、22 类功能，包含未列入 OpenAPI 的 callback、页面、HEAD、静态 mount。
- Checkpoint 用例故障注入阶段关闭 Worker，重启后只由 Worker 执行，不增加
  任意等待来掩盖竞争。5 项定向测试通过。
- 测试观察器全量：307 passed、16 skipped；pytest exit 0，运行期间受记录
  源码未变化。122 个接口被请求命中，26 个未观察到。见 `baseline-tests.xml`
  和 `http-observations.json`；观测不代表业务、Schema、权限或真实模型验收。
- 合成探针发现 Runtime 取消终态覆写、重复 stream 导致重复 Provider 调用，
  以及 Lab/Runtime OpenAPI Schema 覆盖。已登记 `specs/testing/GAPS.md`，
  将进入原子运行时修复，未将这些问题算作通过。
- 本阶段只改测试/规格/治理，尚无应用发布。双端修复部署属于后续待办。

## 完整 verify 重跑

修复后 `bash harness/verify.sh` exit 0：pytest 307 passed、16 skipped，
随后检索、Memory、Recovery、Team、Claude admission 评测及 JS 语法检查全部
执行通过。该次 pytest 收集时 observer 仍为 4 项测试；新增第 5 项参数脱敏
测试另跑 5 passed（`observer-self-tests.json`），不把两次计数相加。
本阶段提交 b9c1917；完整功能验收、运行时缺陷与独立 review 仍未完成。
