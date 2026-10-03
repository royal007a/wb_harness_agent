# HA-0056 验证（返工验证中，未重新发布）

## 2026-10-04 复审返工

- 不再把 exit 5 归为可自动重试；单次 bootstrap 最多 5 秒，保留 exit_code、
  action、attempts。调用方必须是 Aqua，目标 gui 域可查询，当前与恢复 plist
  均符合批准的 label/命令/目录/门禁/会话类型，才允许 bootout。
- 停机后最多 15 秒等待 label 消失及 8765 释放；不杀未知进程。新进程必须满足
  launchd PID=唯一监听 PID，记录启动时间，HTTP 检查前后核对身份及干净提交。
  这是“先释放端口→新启动→核对进程和提交”的本机发布证据，不是新增了带
  release ID 的 health API，也不是不可变发布目录或代码/DB 自动回滚。
- 回退也预检，bootout 错误不忽略。KeyboardInterrupt 写失败回执后停止；
  不因中断自动继续启动。恢复回执明确 code_commit 仍为本次提交，
  config_source_commit 仅表示 plist 来源，code/database_rollback 均 false。
- `review-before.xml`：在 392e103 的归档脚本上运行 5 个新增反例，均因行为失败：
  Background、域不可访问、plist 会话类型错误、未知端口占用仍被旧脚本启动；
  KeyboardInterrupt 后缺失败回执。只为测试名称兼容补了常量和异常别名，未改旧行为。
- `review-targeted.xml`：29 passed，fake launchctl/HTTP + 临时 SQLite，包含
  端口延迟释放、身份/提交漂移、命令超时、恢复错误、门禁/镜像漂移。
- `review-verify-first.log`：首次全量 373 passed / 16 skipped（47.40 秒）；
  `review-verify-final.log`：最后补充旧 PID 拒绝后重跑 exit 0，374 passed /
  16 skipped（46.42 秒），后续定向、确定性评测、JS 与 diff 检查通过。
- 测试入口先误用 `.venv/bin/pytest`，没有将根目录放进 sys.path，收集时
  ModuleNotFoundError: deploy；改用仓库统一的 `.venv/bin/python -m pytest`
  后通过，没有改应用或放宽断言来绕过这次命令错误。
- `review-preflight.json`：在本机只读运行新 preflight，第一条 managername
  检查即因 Background 拒绝，attempts=0；8765 unreachable。没有执行 bootout、
  bootstrap、系统域迁移、模型调用或公网发布。仍需独立复审及兼容调用环境。

以下为历史证据，旧“代码通过”和“登录 GUI 即可恢复”均已被后续复核更正。

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

## 独立复核更正（2026-10-04）

392e103 为 Changes Requested，不再称“代码验收通过”。16 个 mock 用例通过
但未覆盖 OS 会话类型；reviewer 指出并实测 Background 调用方可能导致 gui 域
125，且 exit 5 可为不兼容/已加载的确定性失败。上文“重新登录 GUI 后恢复”
并非已证实的充分条件。user/501 加 Aqua/Background plist 为备选，尚未采用。
待修：bootout 前预检；旧端口退出/新发布进程身份绑定；错误码、attempt 与
deadline 的结构化回执；恢复 bootout 结果核对、中断回执；明确恢复仍用新代码。
旧全量和 staging 通过保留为测试事实，不代表新部署已执行或安全恢复已验收。
