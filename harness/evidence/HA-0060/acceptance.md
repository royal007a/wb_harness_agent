# HA-0060：Team 列表与 Snapshot 不吞故障

2026-10-04（北京时间）；基线8a7e840，固定提交后交mymacclaude独立review。
这是离线代码验证，不是8765/132发布或真实身份/Provider验收。

## 问题与范围

HA-0059独立复审Approved，同时指出其他列表的既有Medium：
Session/Task/Inbox/Recovery以except Problem过滤全部错误，把503当作不可见项。
继续审查发现Session detail/handoff生成Task snapshot时也存在同样路径。

修复：TeamFoundation共享不可变(code,status)白名单；仅5种访问拒绝/归档原因
可以过滤，历史未绑定Task例外仅用于Task检查。未知403/409、码与status不符、
scope错误、缺失引用均保留原错误；数据库/字段异常仍为500。
Recovery在扫描前验证actor，空表也不能跳过不存在/暂停主体的检查。
没有改Channel列表行为、Snapshot选取范围或现有租约过期策略。

## 可复核证据

| 产物 | 结果 | 范围 |
|---|---|---|
| before.xml | 5 failed | 修改生产实现前：4类列表与1个Snapshot的503均错误返回200 |
| targeted.xml | 74 passed，4.43s | 参数化HTTP正反例；不是74个独立产品功能 |
| related.xml | 174 passed，10.97s | 包含新增74项及Team/Foundation/Attention/Session/Recovery/Workbench |
| full-http-observations.json | exit0；575 passed/16 skipped，54.61s | 全量观察器，源码哈希前后未变 |
| verify.log | exit0；575 passed/16 skipped，55.70s | verify全套，另含离线评测、前端语法与diff检查 |

运行命令：

```sh
.venv/bin/python -m pytest -q tests/test_team_list_failures.py --junitxml=harness/evidence/HA-0060/targeted.xml --tb=short
.venv/bin/python -m pytest -q tests/test_team_list_failures.py tests/test_team_read_visibility.py tests/test_team_foundation.py tests/test_team_session_continuity.py tests/test_team_coordination.py tests/test_team_attention.py tests/test_recovery_loop_guard.py tests/test_workbench.py --junitxml=harness/evidence/HA-0060/related.xml --tb=short
env -u ARK_API_KEY .venv/bin/python -m pytest -q -p harness.pytest_interface_evidence --interface-evidence=harness/evidence/HA-0060/full-http-observations.json --tb=short
env -u ARK_API_KEY bash harness/verify.sh
```

旧版行为验证：在8a7e840独立目录放入本轮测试文件，执行
`-k 'does_not_swallow_access_service_failure or snapshot_does_not_swallow_task_access_failure'`。
预期5条均在503实际为200的断言失败；不是导入失败或缺函数。
before.xml是在生产代码仍为8a7e840时直接运行所得；首次编写夹具的422错误已修正，
不将其计为旧缺陷证据。

测试要点：

- 访问检查内部 `_channel` 抛503；内部执行不存在表的SQL和损坏membership字段
  都返回500，没有部分items。不是只替换整个assert_channel_access。
- 五种真实持久状态：Channel撤销/归档、clearance降低、Workspace撤销/归档。
  无损保留其他可见项；按Channel指定的Session请求仍明确拒绝。
- 空/非空均检查缺actor、不存在和暂停主体；可见列表Schema/次序/owner-target
  隔离仍正确。Task/Recovery按Channel共享，不虚报为owner-only。
- scope损坏409、缺失Channel引用404、owner/target列与JSON冲突403，不静默丢弃。
- Recovery到期及Inbox lease过期先发生后遇503：全部相关表保持原样；解除故障后
  同一HTTP读取可以提交过期状态。Snapshot失败不retire Session、不发布Handoff、
  不留下幂等记录。

观察器137/148入口observed，11尚未观测。源码记录是8a7e840+dirty候选状态，
对应source_sha256；不能把结果说成基线8a7e840已具备本轮修复。

## not_evidence / 后续

- 本轮只使用临时DB、TestClient、故障注入；没有正式数据、8765、132、真实
  Provider或凭证。actor_id仍不是认证，运行时门禁不变。
- Inbox/Recovery的GET仍有既有惰性过期写入。没有全面重构成纯只读API。
- HA-0059的Channel持久列/JSON Workspace分歧Low仍未修；snapshot的业务范围及
  全部接口/分支仍待后续审查。没有把缺失数据静默当作已撤销权限。
- 137个入口命中不代表137个功能验收；11个缺口、真实容器/浏览器、模型质量与
  双端部署仍需独立证据。
- 真实发布等待HA-0056兼容本机调用拓扑决定，必须本机先于132；未擅自切换到
  user/system/root launchd域，也未因代码通过宣称发布完成。

复审重点：白名单是否误吞其他状态；Task例外是否串到Session/Inbox；故障是否
留下部分列表/持久过期/交接记录；旧反例是否真能失败。请求只读独立复核。
