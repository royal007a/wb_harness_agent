# HA-0059 Team 列表当前可见性与 HTTP 缺口

2026-10-04（北京时间）。基线2bd4af8，代码与离线验证完成，待独立review。
真实本机/132发布仍阻塞；本轮没有操作launchctl、8765、132、正式DB或Provider。

## 旧反例与修复

在临时DB用公共HTTP创建成员和Channel后，注入现有Schema允许的三种状态：
Channel membership revoked、Channel archived、Workspace clearance降低。
详情分别返回403/409/403且错误码对应，但列表仍返回不可访问Channel的ID和标题。
`before.xml`记录旧实现3 failed，均在列表额外出现hidden项的行为断言失败。

修复 `TeamFoundation.channels`：先保留actor/Workspace前置检查，再逐项使用
assert_channel_access；只过滤已定义的不可见错误，意外错误继续失败而非空过。
没有改详情错误码，不增加认证或在线管理撤销接口，不修改Agent目录语义。

## 验证证据

| 文件 | 结果 | 覆盖 |
|---|---|---|
| before.xml | 3 failed | 未修改2bd4af8实现的三条行为反例 |
| targeted.xml | 18 passed，1.32s | 本轮全部新增HTTP用例 |
| related.xml | 44 passed，3.20s | Team Foundation/Task/Attention/Session/Recovery及本轮用例 |
| full-http-observations.json | pytest_exitstatus=0；501 passed/16 skipped（执行输出58.35s） | 全量TestClient请求观测，源文件哈希前后不变 |
| verify.log | exit 0；501 passed/16 skipped，54.06s | 完整verify、离线评测、前端语法与diff检查 |

```sh
.venv/bin/python -m pytest -q tests/test_team_read_visibility.py --junitxml=harness/evidence/HA-0059/targeted.xml --tb=short
.venv/bin/python -m pytest -q tests/test_team_read_visibility.py tests/test_team_foundation.py tests/test_team_session_continuity.py tests/test_team_coordination.py tests/test_team_attention.py tests/test_recovery_loop_guard.py --junitxml=harness/evidence/HA-0059/related.xml --tb=short
env -u ARK_API_KEY .venv/bin/python -m pytest -q -p harness.pytest_interface_evidence --interface-evidence=harness/evidence/HA-0059/full-http-observations.json --tb=short
bash harness/verify.sh
```

新增验证包括：授权后的Channel详情200、空与非空列表、跨Workspace拒绝、
Workspace创建/成员授予幂等与冲突、缺Key/无效请求/不存在目标拒绝且状态不变、
无效/暂停actor、归档Workspace、Session跨主体/Channel过滤和retired历史、
重启后撤销继续生效（非全局删除）、意外503不吞成空列表、runtime零调用声明。
有动态响应合同的读取/Workspace创建实例均验证合同，未知字段反例被拒；
没有声称所有Team写响应已补动态Schema（其他缺失合同仍须后续审查）。

最新观测136/148，136个有passing-test 2xx，12个未观测，详见GAPS。报告head是
2bd4af8、dirty=true，source_sha256对应本次候选修复，不是基线已有修复的证明。

## not_evidence

- HTTP是临时SQLite + TestClient ASGI行为，不是生产主机联调；状态变化是测试
  注入的有效数据，不是新建了线上撤销/归档功能。
- actor_id未认证。本轮只证明给定协议主体的可见性，不证明真实调用者身份、
  多租户生产隔离、Provider、模型或Agent调度。
- 136入口命中不等于136功能验收；其他入口、所有分支、浏览器、真实容器与双部署
  仍需独立证据。不能把本轮通过当作完整12小时目标完成。
- HA-0056本机拓扑未定，不静默更换到user/root/system域，也不跳过本机部署132。

复审要求：固定提交、只读，重跑旧3反例/新18项及相关回归，挑战过滤是否误吞错误、
主体/Workspace/Channel/Session边界与证据口径，给Approved或Changes Requested。
