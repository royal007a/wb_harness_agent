# HA-0087 完整计划历史：交审证据

基线 `8c13e31`。只改DSH detail内部事件迭代，新增14行helper及1行调用替换；Store公共分页、写路径、运行期计划、前端和Schema不变。尚未合入正在跑全量verify的研究worktree，也未部署。

## 缺陷与实现

详情原先只折叠Store.events默认前500条。600条观察事件后的成功付款Run已有正确终态，但详情仍显示S1/S3/S4 pending；后页拒绝也可能被旧的passed遮住。这是读投影错误，不是原执行或发布失败。

内部迭代继续使用Store分页，每次以实际末条sequence作after，直到空页。整个detail原有Store锁不释放，因此Run、计划、产物和预算处于同一平台读临界区。不重新执行任何事件代表的业务行为，不把历史收据当新的执行许可。

总扫描随历史长度增长；内存只保留有限页与当前计划，而不是整个历史。公共HTTP events仍500条，游标字段是next_cursor。未做大库性能、多进程或外部连接绕过平台锁的验收。

## 已执行

最终测试文件 `tests/test_dsh_plan_history.py` SHA-256：`bbef48b120080d74aadcb1807ad8f0e8324b9f02da667d087f95d97637780dd1`。

| 命令/层级 | 结果 | 证据 |
|---|---|---|
| 新13项 + tests/test_workbench.py | 70 passed，74.37秒 | targeted.xml |
| 恢复整个dsh_runtime.py为8c13e31，git diff确认零差异，原样跑最终新13项 | 10 failed / 3 passed / 0 errors | before.xml |

基线失败是页边界、缺失/旧计划、故障误返回200以及读锁/游标行为断言，不是导入或新helper不存在。499/500边界与无计划历史通过；501、999、1000、1001等后页更新失败。失败后已恢复修复源码。

首轮脚手架有两次更正，不算缺陷证据：临时worktree缺node_modules导致创建503，补既有依赖软链；公开游标误写成next_seq导致前两个正例KeyError，改成真实next_cursor。最终13项基线已重新完整运行，不沿用这些错误结果。

覆盖内容：

- 六个边界的status、evidence_ids、missing_ids、error_codes；公开500条分页未扩大。
- 第9001条才出现计划；短页与稀疏sequence以真实游标推进，不能把页数当序号。
- 前页S3通过、后页拒绝，再取消：详情必须blocked，S4不能误报ready；无计划历史仍null。
- 后页读取失败返回500而不是部分计划，响应无合成秘密；持久快照和total_changes不变。
- 独立写线程在跨页期间等待同一锁，第一次详情对应写入前序号，之后详情才看到新状态。
- 合成桥调用实际平台model/tool/crossing/publish路径，600条观察后3次合成调用成功，计划四步正确；关闭app释放连接/lease后重开同一DB，详情逐值一致。
- GET期间execute、adapter、Provider和凭据哨兵不触发，整库dump和total_changes不变。

最后一条集成路径使用Python合成桥，不是官方SDK或真实Provider；依赖软链只满足既有准入文件检查，没有在这些测试启动DSH子进程。

## 定向突变

M1为完整基线恢复（上表10条失败）。M2–M5通过私有pytest插件，在单独进程中按原方法源码做唯一文本替换再绑定方法；每个进程退出即恢复，不修改共享源码。源码替换均先断言唯一命中，没有用mock返回预设答案替代实现。

| ID | 单点变化 | 结果 |
|---|---|---|
| M2 | after按500累加，不读实际sequence | 1 failed：短页/稀疏历史超过限定读取次数，HTTP500而不是正确计划；测试上界防止探针无穷等待 |
| M3 | step只更新status，不更新证据等字段 | 1 failed：evidence_ids仍为空 |
| M4 | detail取消Store锁 | 1 failed：页读取不持有快照锁 |
| M5 | 忽略后来的blocked步骤 | 1 failed：取消后仍显示旧done |

各有XML，errors=0。这不是全库mutation score。测试用有界事件同步，不以多次随机运行代替并发断言。

## 发布边界

HA-0085/86独立review与冻结版本完整verify仍未完成；原全量已有UI和DSH超时测试失败，尚待最终栈定位，不能用本切片70通过宣称发布可行。临时工作区用于隔离验证，不触碰8876、8765、132、正式库、Keychain和真实Provider。

XML仅规范化机器路径、主机名和行尾，随后重新解析；未保存课程全文、凭据或真实合同。后续合并、完整回归、独立复审和部署另补证据。
