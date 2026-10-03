# 后续：Team幂等回放资格复核缺口

本轮完整性修复之外的只读审计发现，未混入HA-0063修复：

1. 临时SQLite、run_worker=False；用local_admin创建Internal Channel。
2. POST team/sessions，固定key与body，首次201。
3. 仅在临时DB把该Channel的合法status改成archived。
4. GET session detail返回409；同body换新key返回409；旧key却201、body与首次一致。

根因代码：team_session_continuity.py 的 `_idempotent`先返回已存response，
`create_session`里的assert_channel_access在action中，没有重放时执行。
这是“当前资格”与“幂等副作用”的不同要求，需另任务逐项检查Foundation/
Coordination/Attention/Session/Recovery写路径。尚不声称其他路径均已复现。

全部操作位于TemporaryDirectory下，退出自动清理；未触碰正式数据或服务。
没有真实模型调用验证，也没有用本记录中的固定数字冒充调用计数器。
