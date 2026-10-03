# HA-0056 验证（代码通过，双端发布待本机 GUI 恢复）

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

## 冻结版本 392e103 验证

- `verify-frozen-first.log`：355 passed / 1 failed / 16 skipped。失败发生在
  浏览器导航等待 load 超过原有 30 秒，尚未进入会话竞态断言。
- `ui-recheck.xml`：同一用例、代码和超时原样重跑，1 passed（2.52 秒）。
- `verify-frozen-rerun.log`：`bash harness/verify.sh` exit 0，356 passed /
  16 skipped（33.68 秒），随后 v1/v2/adaptive、各确定性评测、JS 语法与 diff
  检查均通过。未扩大超时、跳过失败测试或把 skipped 当通过；两次失败保留。
- 132 独立 staging `/opt/harnessagent-releases/ha0056-392e10356ad9` 的部署
  故障注入与接口清单合计 22 passed；尚未 promotion。
  最后一次补录命令曾遗漏 staging 工作目录，导致两个 import collection
  errors；修正 cwd 后同一冻结版本重跑 22 passed，见 remote-targeted.log。
  这是验证命令错误，不属于代码通过证据；没有据此改应用或测试。

## 真实发布阻塞（2026-10-03 17:16 UTC）

冻结验证后、执行新发布前，本机 `127.0.0.1:8765` 连接被拒，
`launchctl print gui/501` 及本应用 label 均返回 125
（Domain does not support specified action）；`user/501` 可查询，
`/dev/console` 属主为 root。应用 stderr 末尾记录原 PID 60332 正在 shutdown。
这与本机 GUI 会话不可用一致，但没有据此断言谁执行了登出或具体时间。

没有运行新发布、没有修改 launchd domain、没有迁移到 system/root 服务、
没有关闭其他进程。待用户重新登录本机 weberzhao 图形会话后，复核 gui/501，
按原本拓扑恢复，再从干净提交先本机后 132 发布。最后确认的运行版本为
1840639；现在本机离线，132 仍为 1840639 且 health.status=ok、
model_calls_enabled=false。不能将代码验证通过表述为已部署或恢复验证通过。

独立代码 review 可先进行；真实发布验收仍未完成。
