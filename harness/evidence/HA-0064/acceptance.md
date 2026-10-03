# HA-0064 历史收据回放重新核对当前资格

2026-10-04北京时间，基线116a164。25个Team/Recovery写入口候选修复，
尚待固定提交独立review与真实双部署；未操作8765、132、正式DB或Provider。

## 改动与合同

重复请求相同digest时，原来直接返回成功收据；现在在同一事务内先调用必填的
只读授权回调。Foundation拥有共用幂等算法，四个模块显式提供各自当前资格检查。
已有收据不是当前状态/租约，也不允许重新执行动作。25入口及逐项role/owner映射
见specs/testing/TEAM_REPLAY_AUTHORIZATION.md和ADR-0064。

当前identity、Workspace/Channel及membership、clearance、操作role失效会拒绝；
Session owner、Attention target、Recovery owner、Gate reviewer也重新核对。
收据已保存的scope/owner关联漂移返回409/TEAM_REPLAY_SCOPE_CHANGED。首次调用、
不同body冲突、新key完整业务校验保持原样；没有新增身份认证或撤销管理API。

## 已运行证据

| 证据 | 结果 | 解释 |
|---|---|---|
| before.xml | 25 failed | 早期测试的每入口暂停主体反例 |
| before-final-test.xml | 25 failed / 262 deselected，2.98s | 最终测试复制到116a164独立worktree；全部HTTP 200/201≠403 |
| targeted.xml / targeted-http-observations.json | 526 passed，44.16s | 新287项+相关9文件；68入口observed，其中66有passing-test 2xx |
| full-http-observations.json | 1035 passed / 16 skipped，101.94s | 148入口observed且有passing-test 2xx，不是分支/功能验收率 |
| verify.log | exit0；1035 passed / 16 skipped，97.91s | 另跑契约定向、离线评测、前端语法、清单与diff检查 |

verify中的1条AnyIO BlockingPortal弃用告警来自Starlette依赖；未因此改依赖。
任务注册表Schema有效，HA-0063/0064计划与证据路径可取回；全历史注册表已知缺失
HA-0027/l3-admission-gate.json仍为EVIDENCE-PATH-01，不冒称所有历史路径通过。

最终测试SHA-256：7055fc83b80872d42fafa929850efaeca0c3fbe954d99ce7f99d5c0799ee95ff。
旧版worktree测试同SHA，运行后临时副本已清理。重跑方式：将该文件复制到独立
116a164 worktree，再执行：

```sh
python -m pytest -q tests/test_team_replay_authorization.py -k test_replay_rechecks_suspended_actor --tb=short
```

所有25条基线失败都发生在HTTP状态断言处，没有导入/helper错误。两份before XML
只清理空白行尾；最终targeted XML将Workbench测试参数名通过观察器的safe_test_id
改成SHA，避免将大段合成请求放在测试名中；状态、数量、时间和Team用例名不变。
测试编写时曾漏release.reason、把Attention不存在错误码写成不存在的别名；均为
测试编写错误，已更正，不列成业务修复。一次全量命令漏加载观察器插件被CLI拒绝，
随后显式加载插件成功运行，未将该次命令算成测试失败或通过。

观察器两份报告均记录116a164+dirty，139项生产代码/契约/测试/功能映射哈希在运行
前后一致，事后重算无差异；不伪称运行时已有最终提交。16 skipped不算通过。

## 回归覆盖与未证明事项

- 25类真实TestClient HTTP生命周期收据，而非手工构造缓存成功JSON。覆盖主体
  暂停、Workspace撤销/归档/clearance/坏字段、Channel撤销/归档、role降级、
  owner/target/reviewer变更、目标缺失、已保存scope漂移、授权后端503。
- 合法回放逐JSON值等于原收据；成功和失败都比较全部SQLite表及total_changes，
  包括历史done/closed/retired/cancelled、旧claim过期、不重新派生Handoff或Gate。
- 重启后仍拒绝撤销的权限，恢复权限后可再读原收据。已撤销的被授予成员不会被
  管理者读取历史grant收据重新激活。授权管理员读历史grant不要求目标仍active。
- 凭据解析和Runtime Adapter装有拒绝哨兵；run_worker=False且临时SQLite，未对
  宿主正式文件/DB、launchctl、8765、132、网络Provider做操作。
- 只核对收据中已经保存的scope字段。Channel grant仅含channel_id，Recovery仅含
  team_task_id，不包含当时全部上游关系；不能证明任意历史上游重绑都能被发现。
  不做全部嵌套引用扫描、缓存签名/全文完整性、全系统幂等或并发撤销线性化验收。
- 旧成功响应是历史收据，可能仍写active、in_progress或旧lease，客户端不能拿它
  替代当前详情或新执行许可；当前契约不改写历史body。
- HA-0063独立Approved及2个Low已登记，其归档短路/旧scope JOIN边界没有混进本轮
  代码修复。真实部署仍需兼容本机拓扑决定后先本机再132；此处不报上线完成。
