# HA-0068 Pi Product Run 合同与生命周期

2026-10-04，基线868f4b3。固定697ef73已独立Approved，见review.md；真实双部署未完成。
规格：PI_PRODUCT_HTTP_CONTRACTS.md；ADR-0068；新测试test_pi_product_http_contracts.py。

## 已实现

- 五个HTTP入口发布源/静态/动态合同，复用core Task/Run/Event/Artifact；
  请求以pi_review_独立命名空间公开，错误采用local_http_error。
- Gate首次状态检查移到收据事务中；相同key/body返回历史收据，不重新发布。
  取消或另一个Gate先胜出时，迟到的新key不能覆盖终态。
- Adapter结果及回调写入前，在事务内重查取消/时间预算；不回写迟到候选/产物。
- 事件next_seq按本页推进，空页保留输入；HTTP非负int64边界在Store前拦截，
  直接调用仍由Store严格类型/范围防守。详情用倒序迭代读最新Gate，不受500条限制。
  detail/events用同一进程Store锁读取一致快照，不新增DB写入。

## 新鲜证据

| 文件 | 结果 | 说明 |
|---|---|---|
| before-initial.xml/log | 9 failed，0.86s | 修复前生命周期行为失败，非缺模块 |
| lifecycle.xml/log | 9 passed，0.82s | 状态/Gate/分页修复后 |
| new-initial.xml/log | 3 failed/29 passed，6.26s | 草稿测试误把JSON字段顺序当合同；已修测试，不算生产bug |
| before-draft.xml/log | 30 failed/8 passed/2 errors，3.96s | 旧版触发pytest.fail哨兵导致ASGI teardown重复报错，不用作最终基线证据 |
| before-final.xml/log | 30 failed/8 passed/errors=0，5.19s | 最终测试原样回868f4b3；改为调用记录观察，消除上述脚手架噪音 |
| new.xml/log | 38 passed，8.23s | 最终新测试，不依赖Node或真实模型 |
| targeted.xml/log | 185 passed，29.91s | 新测试、既有Pi Run/Adapter/Sidecar、管线、OpenAPI及Workbench共7文件 |
| full.log | 1225 passed/16 skipped，132.22s | 全量；跳过项不算通过 |
| mutation-*.xml/log | 9/9突变被杀死，errors=0 | 详见mutations.md/json，临时worktree逐次还原cmp |

targeted-draft为调用记录修改前的185通过，保留区分。最终测试SHA-256：
`a5de199292992c2f51f6856a0e24c87cf007a2dc6bbd93ed0099be278ad2ace2`。
回基线只复制新测试，保留旧helper/业务/Schema；30个失败不等于30个独立bug，
其中多条由同一空公开声明导致。基线测试SHA与最终一致。

targeted观察60入口，其中59个有passing-test 2xx；full观察148入口且均有
passing-test 2xx。143份源码/契约/测试/功能映射哈希运行前后稳定，最终复核无漂移。
观察器记录868f4b3+dirty，不把候选工作树测试声称为之后提交SHA上的执行。

## 证据边界

- 新测试使用临时SQLite/TestClient和合成Adapter；并发为两个线程共享本进程
  Store，注入时序另外覆盖取消/Gate竞争。不是多进程分布式锁或真实socket证据。
- 新增模拟结果验证控制面发布/Gate，不证明PDF风险判断；既有Faux sidecar测试
  单独纳入targeted，不等于真实模型、费用、法律质量或sidecar即时中止验收。
  该185相关口径依赖本机已安装pi-adapter/node_modules（npm ci）；干净worktree
  没有依赖时为179 passed/6 skipped。新38测试本身无Node依赖。
- Gate回放是历史收据，不是新的执行/授权；当前仍可信本机入口，没有新增principal。
  创建收据JSON逐值一致，不承诺键顺序；Gate字节回放另有断言。
- 最新Gate倒序扫描内存有界，最坏可能扫描整个Run历史；没有宣称索引化JSON查询
  或大规模性能测试。Schema约束形状，不能证明引用存在/同域、游标算术或全局状态。
- 没碰8765、132、正式DB、Keychain、真实Provider或launchctl；仍须按先本机后132
  发布，HA-0056兼容本机拓扑前提不因离线通过解除。
- remaining-empty-responses.json仍有25个API加1个页面的精确空JSON成功声明，
  不包含缺content/非空但宽松声明。全部接口/功能目标尚未完成。
- HA-0067固定868f4b3的独立Approved和2 Low/1 Info另记录于该项review.md，
  不把它挪用为本项Approved。

## 收口检查点

`bash harness/verify.sh`退出0：全量1225 passed/16 skipped；检索2、Agentic2、
adaptive6，确定性评测、准入检查、JS语法和diff检查通过，见verify.log。
测试输出写完后统一清理日志/XML行尾空白、将参数化testcase名称改为摘要，
HTTP观察JSON仅机械压成单行；不修改执行结果、原始nodeid哈希或源码哈希。
两个测试worktree已移除；没有改正式运行配置或数据。697ef73已独立Approved，
Work Item保留blocked（部署待验收），不代表12小时整体目标完成。
