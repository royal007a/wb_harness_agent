# HA-0073 外部 Skill HTTP 合同与损坏包

业务基线5241fe4；d65cd06只登记HA72复审/补跑证据，不改业务。候选由包含本文件
的提交固定，尚待独立review与双部署。规格EXTERNAL_SKILL_HTTP_CONTRACTS.md、
ADR-0073；目标是现有四入口，不接Agent Loop或Product Run。

## 实现

- runtime、包列表、登记三类空成功声明补源/静态/动态合同；执行审计收紧。
  四入口default及动态422绑定当前local_http_error，source_label复用源约束。
- ZIP只接受无加密stored/deflated；损坏deflate、manifest ValueError/RecursionError
  转422。非法UTF-8也属ValueError子类；意外RuntimeError不吞成输入问题。
- 没有增加运行权限/网络/凭据，也没有改幂等或执行事务。数据库回滚、历史收据、
  成功计数与单执行锁原有行为此次补证据，不虚报新实现。

## 可复跑证据

测试文件SHA256：338910f6394a44b7dd4f0adc6038efb55aef13df59ff752cf9cad0c232c88511。

| 证据 | 结果与版本 |
|---|---|
| new.log/xml | 最终缺default显式断言之前：48 passed，8.27s |
| before-final-assertions.log/xml | 补ZIP标志位前48项原样回5241fe4：48 failed/errors0，全部断言失败 |
| targeted-final.log/xml | 补ZIP标志位前5文件188 passed/5 skipped，17.52s |
| full.log/xml | 增加缺default显式断言前：1418 passed/16 skipped，159.03s |
| mutation-results-final.json | 补ZIP标志位前12个定向突变全部被断言抓住，errors0 |
| flags-before.log/xml | 补强加密/patch位后修复前：2 failed/48 deselected，均500≠422 |
| before-release.log/xml | 最终50项原样回5241fe4：50 failed/errors0，全部断言失败 |
| targeted-release.log/xml | 最终5文件190 passed/5 skipped，17.24s |
| mutation-results-release.json | 最终50项版本的12个定向突变均被断言杀死、errors0 |
| verify-release.log | 最终50项版本verify退出0，全量1420 passed/16 skipped；初版verify/final日志保留 |

命令：`.venv/bin/python -m pytest -q tests/test_external_skill_http_contracts.py`；
相关再加test_external_skills.py、test_workbench.py、test_openapi_contracts.py、
test_local_deployment.py；全量与`bash harness/verify.sh`独立运行。

基线失败不是等量的独立bug：多数因空成功Schema或旧错误信封；压缩/解析几个
分支在HTTP状态断言处失败。早期before.log/xml是39项草稿，重启测试曾错用
不存在的Store.path；before-final是48项但缺default先报KeyError。两者都不计作
最终行为反例，最终版本显式断言声明存在、用临时路径重启，同文件无导入/脚手架
错误。target-initial的深JSON错误码断言过窄也已更正并保留，不能算生产回归。

12个突变逐次在独立worktree运行、恢复并cmp；提前commit后重新BEGIN，确保
seed正常，失败落在执行计数的持久快照断言。只是1–8个定向用例/突变，不是全库
mutation score。manifest解析上限的确定性用例注入ValueError/RecursionError，
另有真实坏JSON/超长整数，不能把模拟异常称为跨Python版本真实上限测试。

targeted/full初版observer各148份源码摘要运行内稳定；后续增加缺default的
显式断言与两个ZIP标志位用例，因此旧observer不代表最终测试SHA。targeted-release的
148份源码/Schema/测试/映射摘要运行内及事后核对，观察53个入口；旧full观察
148个入口只是命中记录，含拒绝，不是验收率。清单剩19个API+1页面空JSON成功
Schema，缺content及非空但宽松声明另计，不能宣称全部合同已补完。

最终targeted-release的148份摘要经比较全部匹配当前文件，sources_unchanged_during_run
为true。最终12份突变XML与before-release逐一解析，testcase/failure结构正常，
没有error或导入失败；只做路径替换，不再用跨标签正则改写XML testcase名称。

## not_evidence

临时SQLite、TestClient及合成Sandbox；不执行上传entry.py，不启动真实容器，
不碰正式DB、Provider、Keychain、8765/132。五项真实Docker测试仍跳过。
重启是关闭TestClient后对同临时DB创建新app，不是OS进程重启。失败原子性比较
持久表，total_changes包含回滚动作，不能单独作为泄漏判据。

runtime/列表会探测镜像；本套用替身，不称真实Docker可用或零I/O。代理/非回环
拒绝沿用相关旧测试；执行审计backend可选是旧收据兼容，不证明运行时逐响应验证。
文件目录与DB不是跨资源事务，登记DB失败可留下摘要目录；执行后DB失败重试
可再次执行（测试明确计数2），不承诺exactly-once。当前单服务执行锁不是多实例
或多租户锁。未测真实socket、容器资源极值、并发登记、孤儿清理、供应链或部署。
兼容本机拓扑尚待批准；不能跳过8765部署132，也未启用任何模型门禁。
