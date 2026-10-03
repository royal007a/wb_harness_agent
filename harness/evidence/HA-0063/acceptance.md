# HA-0063 Team持久记录完整性

2026-10-04北京时间，基线7ac1498。固定116a164已获mymacclaude独立Approved，
附2个Low，详情见review.md；批准只涵盖代码与离线测试，不涵盖实际发布。
没有部署，没有变更正式数据、launchd域、认证、运行时或模型门禁。

## 修复

五种Foundation记录读取时复用现有Schema检查结构、类型、枚举和额外字段，
并核对SQL行的主键/关联键。未知status不再冒充合法暂停/归档/撤销；列和JSON
身份/scope不一致不再出现在错误目录。失败统一500/TEAM_STATE_CORRUPT，消息
不含损坏正文或标识。Channel列表改用共享(code,status)过滤，503不吞成空列表。
合法inactive的访问拒绝与管理目录展示保持原样；不自动修数据。

## 验证

| 证据 | 结果 | 意义 |
|---|---|---|
| before.xml | 18 failed | 编码前基线HTTP行为反例 |
| before-final-test.xml | 18 failed / 46 deselected，1.39s | 最终测试复制到7ac1498独立worktree，仍全部按行为失败 |
| targeted.xml / targeted-http-observations.json | 182 passed，10.97s | 8个相关文件，其中新文件64项；43入口有passing-test 2xx |
| full-http-observations.json | 748 passed / 16 skipped，73.61s | 148/148 observed且有passing-test 2xx；不等于功能验收率 |
| verify.log | exit0；748 passed / 16 skipped，73.30s | 完整verify，含离线评测、前端语法、接口清单与diff检查 |

最终旧版反例：5种对象×3种非法status=15项，Channel列/JSON错域2项，code相同但
status=503被误吞1项。均在HTTP状态/内容断言处失败；没有导入或缺helper失败。
可把最终`tests/test_team_state_integrity.py`复制到独立7ac1498 worktree后运行：

```sh
python -m pytest -q tests/test_team_state_integrity.py -k 'unknown_status_is_corruption_not_revocation or channel_sql_scope_mismatch_cannot_move_channel_between_workspaces or channel_filters_code_and_status_together' --tb=short
```

两份before XML仅清理pytest失败文本的空白行尾；断言、时间和计数未改。
最终基线worktree的测试文件与主仓库逐字同哈希，运行后清理临时副本；报告保留。
测试文件SHA-256：9c5584d9b4845390623aa48f3016c580c748166aa3c05913d4cdb5f817f98829。
新测试初写曾因helper参数kind和待变更的kind字段重名失败，已修测试helper名称；
不将这个测试编写错误记成业务缺陷。

两份观察器记录7ac1498+dirty，138项源码/契约/映射哈希运行前后一致，事后重算
无差异；不是谎称测试时已有最终新SHA。verify另有1条Starlette使用已弃用AnyIO
别名的依赖告警，未改依赖；16 skipped不算通过。

## 覆盖与边界

- 除旧反例，覆盖缺字段、额外字段、非法JSON/非对象、非法role/data_class/version，
  SQL键不符，非调用者目录/详情数组损坏，合法inactive仍可由admin查看。
- 空列表扫描前校验主体；新幂等键写入遇到损坏无新增Session/Handoff/幂等记录；
  Inbox lease与Recovery过期后的访问失败全部回滚，没有部分items或残留过期写入。
- 临时SQLite + TestClient，凭据与Runtime Adapter/native入口有测试哨兵；未使用
  正式DB、8765、132、真实Provider或容器。不用静态runtime零字段证明零外发。
- 仅验证实际读取到的Foundation记录；不是全库孤立引用扫描、跨模块完整性校验、
  日期format/真实性或身份认证。Schema变更需要迁移，坏数据由权限拒绝变500是
  明确的兼容性变化。
- 幂等缓存重放仍可能跳过当前资格检查：TEAM-REPLAY-01已用Session临时DB复现，
  见replay-followup.md。此轮新key写入回归不能证明旧key重放已安全，另任务处理。
- HA-0062已独立Approved；复审Low及历史before报告版本限制登记在其review.md。
- 任务注册表Schema有效，本轮HA-0062/0063计划/证据路径均存在；全历史引用检查
  另发现HA-0027缺l3-admission-gate.json，已登记EVIDENCE-PATH-01，未冒称全库通过。
- 本机Background/gui域阻塞未解除，双部署未执行。必须明确兼容拓扑后先本机再132；
  不把测试通过或review通过当作已上线。
