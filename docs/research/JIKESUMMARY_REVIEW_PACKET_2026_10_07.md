# DSH课程优化复审入口

本轮包含四项运行行为修复、一项评分器修复和两项测试加固。未部署，不能把定向通过或课程阅读当作发布验收。研究索引见[JIKESUMMARY_INDEX](JIKESUMMARY_INDEX_2026_10_07.md)，源码基线5939e5d；第五轮完整测试固定a5ec114，第六轮固定3036543（含HA92清理修复）。被测工作树保持冻结，研究文档单独更新。

## 固定切片与最小复跑

下列pytest命令前缀均为`.venv/bin/python -m pytest -q`。用隔离worktree、临时SQLite、既有锁定依赖；不要跑真实Provider或重启服务。 macOS临时根需解析为真实路径，已安装的node_modules不是Git内容，worktree缺依赖导致skip不等于功能通过。

| 顺序 | 固定提交 | 最小文件或selector | 重点 |
|---|---|---|---|
| HA85 | fd0b323；1ae1a6a只更正XML | tests/test_dsh_crossing_retirement.py | unused retired与in_flight unknown；正常退役和终态同事务；取消不等Provider；事件sequence重读 |
| HA86 | b080743 | tests/test_dsh_startup.py | SDK显式初始化60秒仍受Run期限；固定错误信封不泄露SDK错误或stderr；不把启动错误叫Provider故障 |
| HA87 | 8d1a8ba | tests/test_dsh_plan_history.py | 499/500/501/999/1000/1001；最新计划、晚创建和拒绝；稀疏游标；GET锁与零写入 |
| HA88 | 85745bb | tests/test_dsh_payment_scoring.py | 30与300、自然日与工作日；失败无产物不算无误报；ID必须唯一且与labels完整一致 |
| HA89 | 4b8ec1e | tests/test_dsh_runtime.py -k timeout_while_provider_waits | 先到达合成Provider再触发期限；协程取消、调用unknown与资源清理 |
| HA91 | a5ec114 | tests/test_dsh_runtime.py -k 'cancel_while_provider_waits or sigkill_then_recover' | 明确挂起代替0.8秒返回；设置等待与取消期限分开；finally回收测试线程；kill后恢复断言不放宽 |
| HA92 | 3036543（43dd049..3036543，含e64b03d初版） | tests/test_dsh_cleanup_errors.py tests/test_dsh_startup.py | 清理故障不覆盖主异常；正常返回不得藏在外层except后冒充成功；拒绝升级信号，其他资源仍释放；活目录保留 |

每项对应`harness/evidence/HA-编号/acceptance.md`，含SHA、失败基线、突变方法和边界。HA85在HA86之前的SDK失败原样保留；后来的联合114项才包含最终11条HA85测试，不倒填最初结果。

HA88后续实际官方SDK重跑见`harness/evidence/HA-0088/sdk-evaluation-followup.md`及JSON（036f338）。21个合成case、77次脚本Provider调用，11成功、10按DSH_FINDINGS_INVALID拒绝；隐含例外词表指标仍0/2。不是模型质量提升，也不是真实Ark验收。

## 发布门禁与资源约束

五轮完整运行均未通过，失败与中断日志保留在HA85/HA89/HA92。第四轮3失败/1804通过/22跳过，取消和崩溃测试未抵达注入阶段，intent子进程5秒超时；其后3项独立复跑通过，不拼接成全量成功。第五轮a5ec114为3失败/1804通过/22跳过：UI详情GET中止、两个startup错误分类失败；无-x、不跳过UI、未调整intent期限，诊断插件只透传记录时序。UI原用例隔离通过也不算已修复根因。HA92定向通过不能替代下一轮完整验证。

8876只读核对：release ad957fb888789eccc1150d0ea0df643cce8047c9，label和监听PID64681，无进行中DSH Run。此观察不是未来重启许可的身份快照；真正停服前必须重新核对。8765、132、生产库和Keychain未操作。

第六轮3036543已结束：1失败/1821通过/22跳过，2230.42秒，exit 1。唯一失败是UI会话选择click超时；失败后状态快照显示已选中、请求结束且发送按钮可用，不能据此把超时忽略为通过。原因尚未定位；保留原断言、原期限和全部UI测试，也不将主机负载直接认定为根因。因pytest失败而未运行的verify后续步骤，随后在同一源码上单独执行exit 0，不能拼接为verify全绿。日志和命令见[完整验证记录](../../harness/evidence/HA-0089/full-verification-followup.md)。

发布时不能直接复用`deploy/verify_dsh_local.py`的旧HA77浏览器回执来证明新版本。应绑定本轮release、新Run ID、至少多轮工具往返、预算、产物哈希与无残留目录；新旧证据分开。需要先通过独立复审和完整门禁，再备份当前实际数据库、记录回滚点并只切8876。

## 复审输出

已收到的明确结论：HA85 fd0b323、HA86 b080743、HA87 8d1a8ba、HA88 85745bb、HA89 4b8ec1e均为Approved，限各固定切片的代码或离线测试。各目录`independent-review.md`分别记录复审方报告的重跑范围和Low，未将未收到的独立原始日志视为现有证据。

HA86的高负载startup偶发失败尚无独立失败断言，不能和作者第五轮清理异常未经核对就合并归因。HA88的@2官方SDK评测已保存于036f338并补发给复审方，尚待其确认附件。

后续收到HA91 a5ec114和HA92最终3036543的单独Approved：分别独立运行2项和15项通过，范围和Low见各自independent-review.md。因此HA85–89/91/92全部获得固定切片批准；阅读报告和完整发布门禁仍未通过。中文条号最终编号HA90（da56602/ebc88c6历史上先用HA93/94，编号冲突后更名，不改写历史），不属于这些批准。Claude的HA93凭据、HA94上下文反馈及后续切片仍在独立分支，不自动合并。

每个切片单独给Approved或Changes Requested，列出实际重跑范围、未覆盖边界和阻断项。请同时提供本地结论文件路径，避免聊天卡片只显示标题。运行代码批准、阅读报告批准、真实模型与部署验收是四种不同结论；未检查部分不默认为通过。
