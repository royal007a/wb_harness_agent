# HA-0056 验证（进行中）

基线 e603c58，应用双端 1840639。规格为 LOCAL_DEPLOYMENT_RECOVERY.md。

`deployment-before.xml`：旧助手两个反例失败。一次暂态 bootstrap=5 就转入
回退，而回退也遇到 5 后退出；另一例没有恢复健康验证或失败回执。
测试用临时目录、SQLite 和 fake launchctl/HTTP，不操作用户服务。

实现只重试 bootstrap=5，共用 30s 绝对 deadline；命令超时或其他退出码
不重试。正向与回退都校验 health、禁用模型/工具门禁以及原 Colima 镜像。
恢复只针对 plist，不回滚代码或 DB。失败原发布仍失败，单独保存恢复结果。

`deployment-after.xml` 为首两个反例修复后通过；扩展永久错误、命令超时、
健康超时、恢复失败、准入/镜像漂移与脏工作区等，见 deployment-expanded.xml。
完整验证、固定提交双部署与独立 review 尚待完成，不能把模拟故障当 OS 级证明。

冻结版本 `deployment-freeze.xml`：16 passed，追加检查 bootout 命令超时、
暂态 sandbox_unavailable、失败阶段与退出码。`final-targeted.xml` 为此前
15 个部署用例 + 6 个接口清单检查，共 21 passed。

首轮 `verify.log`：353 passed / 1 failed / 16 skipped，exit 1。该次采集为
14 个部署测试版本；运行期间进一步补齐的最终 16 项另行验证。唯一失败为
`test_fixed_fixture_evaluation_is_repeatable_and_redacted` 的 CLI 子进程超出
既有 5 秒等待，并非部署断言。同期观察到约 20 GB swap 使用和很少空闲内存，
只能作为环境背景，不能据此忽略失败。未修改原测试的 5 秒上限；需原样复跑及
冻结代码的全量重验后才发布。完整审查目标仍在进行中。
