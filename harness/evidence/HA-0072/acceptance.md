# HA-0072 图写入合同与来源时间

基线a78d535（业务同7a03b99），候选固定于包含本证据的提交，待独立review；测试规格
specs/testing/MEMORY_GRAPH_WRITE_CONTRACTS.md，ADR-0072。

## 实现范围

- 两个图写入POST的成功Schema原已存在。本轮动态增加default/改绑422，静态
  由旧Error改为当前local_http_error；不是新增接口或减少空成功声明数量。
- 去重audit_id=null、新建audit_id为memaudit引用，两分支机器约束明确。
- 新key的Entity/Relation及端点支撑检查排除未来Source，与读侧一致。
  同key继续HA70历史收据语义；未删除的过期/撤回证据不是重新执行许可。
- header1..128、去重规范化、事务保护本已实现，这次补正反例，不虚报新能力。

## 实测证据

初版40项基线24失败/16通过；初版修复40通过。补时间相等及同key重试后42项。
最终固定基线a78d535：26失败/16通过/errors0，全部行为或契约断言；
没有缺符号/导入失败。错误负例补强后原样重跑结论不变（before-final-errors）。
最终测试SHA256：439ad68867d81fc07c37aa67253356a39c363e59dcbcf0cb805fbe7bc2d5b29a。

突变初轮14项杀死12项；静态改回旧Error的2项存活，因为合法错误形状同时满足
新旧Schema。补独立非法错误字段后两个突变均被杀死；初轮记录保留。
提前commit突变的前两轮在seed时失败，不算事务证据；改为commit后重新BEGIN，
seed才正常。mutation-valid-commit-before-receipt的两个失败均落在持久表快照
断言（不是准备数据），证明目标写入的半提交能被抓住。最终14项有效突变全部
被杀死、errors0，逐次恢复cmp。ignore-fact-bank因404变409被抓住，另外的Source
Bank检查仍能阻止写入；不能称这个单点突变造成实际跨Bank写入。
一次定向命令使用不存在的test_memory_temporal_read.py，退出4/no tests；
targeted-invalid-path.log保留，不计作通过。改用test_memory_temporal_read_safety.py。

| 证据 | 结果 |
|---|---|
| new.log/xml | 初版40 passed |
| before-final-errors.log/xml | 最终42项原样回基线：26 failed/16 passed/errors0，6.09s |
| targeted-final.log/xml | 10文件242 passed，27.83s，最终错误字段负例已加入 |
| full.log | 补强错误字段负例之前42项版本的全量：1370 passed/16 skipped，143.39s |
| verify.log | 最终版本bash harness/verify.sh退出0，全量1370 passed/16 skipped，152.82s；离线评测/准入/JS/清单检查通过 |
| mutation-results-final.json | 13项最终突变日志加1项valid早提交日志，非全库mutation score |

运行全部采用a78d535+dirty候选，不倒填提交号。observer旧targeted/full均147份
源码摘要运行内稳定；后续仅新测试文件增加错误字段反例，所以它们不是最终测试
SHA的记录。最终targeted-final的147份源码/Schema/测试/映射摘要运行内及事后
核对均一致。targeted观察62入口、full观察148入口，不是验收率或全部功能覆盖。

## not_evidence

临时SQLite、单进程TestClient、合成Source/Fact/Entity/Relation；未用正式数据、
Provider、Keychain、真实socket或远端。重启是关客户端后对同一个临时DB建新app。
故障后原子性比较持久行，total_changes会计入回滚动作，不能用它判定持久泄漏。
时间失效场景部分以直接更新合成DB构造，未来Source及时间相等用真实Retain。
历史回执为提交当时快照，不证明当前可用；Schema不证明引用存在/同域/真实知识。
不做FTS影子表擦除、多连接并发、大库性能、完整图读契约或自动GraphQA。
双部署仍受兼容本机拓扑阻塞，不能跳过8765直接发布132；所有模型门禁保持关闭。

## 独立复审与证据更正

5241fe4已独立Approved，细节见review.md。原valid早提交XML被脱敏截坏，
不可用；对应日志保留。已在5241fe4重新运行同突变得到2项持久快照断言失败，
新mutation-commit-receipt-rerun.xml可解析，最终manifest改引用它。上表的原
valid XML不再计作有效机器证据；不倒填原运行时间。代码批准不包含双部署。
