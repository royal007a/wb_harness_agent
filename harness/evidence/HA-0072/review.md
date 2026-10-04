# HA-0072 独立复审及证据修正

mymacclaude对5241fe4给出Approved，2 Low为证据问题。来源消息
om_x100b632eaadf00a4c32578aaef1f90c。以下复审结果来自对方，不冒充作者重跑。

- 新42项SHA一致；指定5文件176通过；同文件回a78d535为26失败/16通过/errors0，
  全部断言失败但不是26个独立bug。独立worktree全量1364/22，6项额外skip源于
  没有pi-adapter/node_modules；总数1386与作者1370/16相同。
- 32个时间/Bank探针通过：Source时间±1微秒和时区、Fact有效期端点、Relation
  两端来源、同key修正后重试、跨Bank、supersede后新请求拒绝/旧收据回放。
- 三套合同、触发器audit故障全事务回滚、历史收据及删除后重启均通过。
- 对14份突变日志的断言阶段逐一核对；另7个独立突变杀死6个，单去Source Bank
  查询约束因Fact Bank约束仍在而判断为等价突变。不代表全库mutation score。

## 证据修正（作者实跑）

原mutation-valid-commit-before-receipt.xml脱敏损坏，只有一个testcase却有两个
failure，不能作为机器证据。保留原文件供追溯，但明确无效；原.log没有此问题。
在固定5241fe4隔离worktree重新应用mutation-plan同一个commit+BEGIN突变，
运行 `pytest -q tests/test_memory_graph_write_contracts.py -k 'graph_failure_rolls_back and receipt'`：
2 failed / 40 deselected / errors0，均落在289行持久快照断言，seed成功。
新mutation-commit-receipt-rerun.xml通过xmllint；mutation-results-final已改引用新件。
补跑之后还原memory.py并cmp相等。新证据是新的运行，不冒充原时间的文件修复。

突变是定向1–5个用例，不是全量；10文件242没有被复审重跑。Entity/Relation自身
未来时间的写入策略不在此修复内，多连接并发和双部署仍未验证。
