# HA-0072 图写入HTTP契约及支撑来源时间边界

基线a78d535（业务同7a03b99）。HA71已独立Approved，部署仍阻塞。

1. 先按ADR-0072与测试规格覆盖Entity/Relation三套响应契约、错误与回放。
2. 记录基线反例：错误响应漂移、去重audit分支、未来Source支撑；header回归。
3. 补公开契约及最小业务修复，不重做图召回或认证，不修改正式数据。
4. 运行定向Memory/Workbench、全量verify、独立worktree基线和定向突变；
   固定提交交mymacclaude。明确Success Schema原已存在，不虚报空接口减少。
5. 兼容本机拓扑获准后先8765再132部署；本任务不绕过该边界。

实现及验证完成：新42/相关242通过，基线26行为失败/16通过/errors0；14有效
突变（静态错误约束负例补强、提前commit重新BEGIN后到快照断言才算有效）。
全量1370 passed/16 skipped，verify退出0。固定提交交独立review，待兼容拓扑
后的双部署；证据harness/evidence/HA-0072/acceptance.md，未启用任何模型门禁。

5241fe4已独立Approved。损坏的早提交突变XML已标无效，固定版本隔离重跑
2项均在持久快照断言失败，新XML通过解析并替换manifest引用，详见review.md。
仍只阻塞于双部署，不重复申请代码review。
