# HA-0066 Memory / Research读取合同

2026-10-04，基线e6e1fb9。实现/离线验证候选，尚未独立review或双部署。
规格MEMORY_RESEARCH_READ_CONTRACTS.md，ADR-0066，新增测试文件
tests/test_memory_research_read_contracts.py。

## 实现

7项：Memory runtime、Bank列表/创建/详情及三类Research列表。源合同复用Bank/
Run定义；静态与动态绑定同一成功形状及现有错误信封。静态文档补两个已存在的
GET路径，不是新增业务API。Research仅本引擎根Run，parent_run_id缺省/null均可；
没有复制或改变Product终态、运行权限、业务响应。运行时仍没有通用Schema拦截器。

Memory实际M3-B状态包括FTS可用/失败及semantic档案投影。档案可admitted，但
runtime_enabled仍false，model_calls/external_calls只是档案记录而非遥测。
详情counts是已存Source/Fact数量，撤回仍保留，删除才减少；不返回正文。

## 验证证据

| 文件 | 结果 | 说明 |
|---|---|---|
| before-initial.xml/log | 7 failed / 27 deselected，1.31s | 实施前7项旧公开Schema接受空对象 |
| initial.xml/log | 3 failed / 31 passed，5.45s | 首版错误要求根Run显式parent_run_id；实测后修正为缺省/null，保留失败证据 |
| new.xml/log | 36 passed，6.41s | 最终新增用例 |
| before-final.xml/log | 36 failed，5.52s，errors=0 | 最终测试原样放回e6e1fb9；旧公开声明失败，不是导入错误 |
| targeted.xml/log、targeted-http-observations.json | 283 passed，34.56s | 9文件（含Workbench）；74入口有passing-test 2xx |
| full.log、full-http-observations.json | 1131 passed / 16 skipped，111.76s | 148入口有passing-test 2xx，不是功能或分支验收率 |
| mutations.md、mutation-*.xml/log | 8/8突变被杀死，errors=0 | 独立worktree，逐项恢复并cmp校验 |

完整`bash harness/verify.sh` exit0（verify.log）：1131 passed / 16 skipped，
112.54s；检索状态2、Agentic状态2、adaptive6项与其余离线评测、准入拒绝检查、
前端语法及diff检查均通过。仅既有AnyIO弃用告警。历史EVIDENCE-PATH-01没有因此
被修复；不声称所有历史任务证据完整。

最终新增测试SHA-256：f93fb0df711522a3394760487b829652a68176546e91887d7cda400dbca6777f。
基线worktree仅复制该文件，已有helper保留基线版本；两端SHA一致。36失败多次
命中了同一空Schema问题，不称为36个独立生产bug；原样pytest可复现。曾因从
基线目录按相对路径复制新文件，导致一次pytest未收集（exit4），修正路径后才
生成此最终报告，不把那次基础设施错误作为反例。突变与基线worktree均已清理。

targeted.xml中31个Workbench参数名以safe_test_id哈希化，避免包含大段合成输入；
失败报告与日志仅清理行尾空白，测试结果未改写。观察器记录e6e1fb9+dirty，
141个源码/契约/测试/映射哈希前后一致；不把dirty结果伪装成最终提交SHA的运行。

## 不证明什么

- TestClient+临时SQLite，不是真实HTTP socket/浏览器/Provider/CLI/容器/部署。
  Native只通过临时测试准入创建queued元数据、取消与重跑，不执行模型；关闭环境
  门禁后读取历史，重启仍保持。stream_native_research/凭据/Adapter及重启后
  Service.execute有哨兵。两个模拟研究引擎则实际执行固定函数并验证完成状态。
- FTS退化使用内存状态故障注入，不是证明此开发机缺FTS；semantic异常通过临时
  缺失文件、非法JSON/Schema、合法admitted文件走真实投影函数，不改正式准入档案。
- Schema约束和当前元数据过滤不是身份认证，也不自动修复损坏DB。未验证全部
  Memory生命周期、研究POST/详情、Pi响应和其他尚为空的公开声明。
- 16 skipped不算通过；测试中的PDF只是准入摘要样本，不是PDF解析或真实研究。
- 独立复审、真实双部署仍待完成；本轮不碰8765、132、正式DB、Keychain、launchctl。
  先本机后132的部署前提不变，HA-0056拓扑阻塞没有被离线测试解除。
- remaining-empty-responses.json额外程序枚举到35个API成功响应仍明确声明空JSON
  Schema，另有1个页面；这不是所有缺口的数量（不含缺content或非空但不完整的
  Schema）。用于后续任务，不把本轮7项修复称为全部接口合同完成。
