# DSH课程优化复审入口

本轮包含三项运行行为修复、一项评分器修复和两项测试加固。未部署，不能把定向通过或课程阅读当作发布验收。研究索引见[JIKESUMMARY_INDEX](JIKESUMMARY_INDEX_2026_10_07.md)，源码基线5939e5d，当前运行代码4b8ec1e，第五轮完整测试固定a5ec114。

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

每项对应`harness/evidence/HA-编号/acceptance.md`，含SHA、失败基线、突变方法和边界。HA85在HA86之前的SDK失败原样保留；后来的联合114项才包含最终11条HA85测试，不倒填最初结果。

HA88后续实际官方SDK重跑见`harness/evidence/HA-0088/sdk-evaluation-followup.md`及JSON（036f338）。21个合成case、77次脚本Provider调用，11成功、10按DSH_FINDINGS_INVALID拒绝；隐含例外词表指标仍0/2。不是模型质量提升，也不是真实Ark验收。

## 发布门禁与资源约束

四轮完整运行均未通过，失败与中断日志保留在HA85/HA89。第四轮3失败/1804通过/22跳过，取消和崩溃测试未抵达注入阶段，intent子进程5秒超时；其后3项独立复跑通过，不拼接成全量成功。第五轮正在冻结a5ec114运行，无-x、不跳过UI、未调整intent期限；诊断插件只透传记录时序。

8876只读核对：release ad957fb888789eccc1150d0ea0df643cce8047c9，label和监听PID64681，无进行中DSH Run。此观察不是未来重启许可的身份快照；真正停服前必须重新核对。8765、132、生产库和Keychain未操作。

发布时不能直接复用`deploy/verify_dsh_local.py`的旧HA77浏览器回执来证明新版本。应绑定本轮release、新Run ID、至少多轮工具往返、预算、产物哈希与无残留目录；新旧证据分开。需要先通过独立复审和完整门禁，再备份当前实际数据库、记录回滚点并只切8876。

## 复审输出

每个切片单独给Approved或Changes Requested，列出实际重跑范围、未覆盖边界和阻断项。请同时提供本地结论文件路径，避免聊天卡片只显示标题。运行代码批准、阅读报告批准、真实模型与部署验收是四种不同结论；未检查部分不默认为通过。
