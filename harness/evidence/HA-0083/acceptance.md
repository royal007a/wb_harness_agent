# HA-0083 验证记录

基线 5a83d38；任务 B，不包含 A2 证据续跑。实现、评审、部署分别记录，不以本文件代替尚未完成的验收。

## 实现边界

- 平台签发 Run/generation/model-round/tool-ordinal 身份，DSH 工具 ID 换成平台票据；原模型 ID 仅摘要关联。跨轮重复 call_probe_0 不被误去重。
- 同票同内容在活动 Run 内回放首次完整响应，仅内存缓存。返回 notice/提交编号保持首次值，不重新调用工具或预算函数。
- dsh_crossings 和 dsh.crossing 仅元数据；收据状态与审计同事务。工具动作完成到收据完成之间的故障保守 unknown，不重发，不声称跨调用 exactly-once。
- 取消/截止先于缓存回放；恢复将 in_flight→unknown、issued→failed。原预算 sent→unknown 保留未知预留。
- 私有协议升级，公开 HTTP 接口和上游 SDK 不变。旧 Run 可读，缓存不跨进程恢复。

## 离线证据

- 新增 tests/test_dsh_crossings.py：20 项，覆盖并发、改参、跨 generation、取消、收据提交故障、审计原子性、重启未知预算、缓存丢失、重复 execute 不退役其他执行代次。
- 官方 DSH SDK + 合成 Provider：free/payment 两种模式，每次 callback 人为重复一次，逐值比较首次结果并断言 DB total_changes、预算不变，提交次数不增加。
- 独立真实 loopback HTTP 探针：合成 Python 子进程对模型、工具各投递两次，平台实际执行各一次。这一条不是官方 SDK，也不是真实 Provider。
- 定向内存突变：harness/dsh_crossing_mutations.py，7/7 被捕获，XML failures > 0、errors=0。每个突变只跑对应的定向用例，不是全库 mutation score；不修改源文件。
- DSH 全部测试文件 + test_workbench.py：262 passed，见 targeted.xml/log。
- 初次全量 3 failed / 1725 passed / 22 skipped：两个旧压缩测试的 6500 字符窗口被更长的平台票据挤满，先安全失败，未到其进展断言；仅测试窗口分别调为 7600/7100，生产 64000 不变。第三条是新 HTTP 探针继承 macOS 系统代理，已在探针显式禁用代理。修复后这 36 项定向通过。
- 最终独立运行 verify.sh exit 0：1729 passed / 22 skipped；后续评测、准入检查、Node 语法检查和 git diff --check 都通过，见 verify.log。未设置真实 Provider 凭据，未执行真实调用。
- 旧对抗探针按新信封升级，仍验证业务拒绝原因；不保留不带票据的兼容旁路。没有声称新文件原样放回旧版能得到行为反例（旧版没有收据模块）。

## 独立复审

mymacclaude 对 7ad0793 给出 Approved，隔离 worktree 复跑 crossing + HA-0082 计划与探针，43 passed；没有重跑真实 Provider 或部署。

两个非阻塞边界已登记 DSH-CROSSING-01/02：SDK 在本地拒绝非法参数、从未投递工具时，下一轮报 PREDECESSOR_PENDING 并安全失败；预签发而未使用的下一模型票据在 Run 终态后被标为 failed，这不是实际发出的模型调用失败，不增加预算调用次数。后续再细分 unused/retired 及事件顺序，本轮不修改已批准的运行代码。

## 部署与真实调用

- 8876 从 6ec6180 切换至 ad957fb（运行代码与已批准的 7ad0793 一致）。发布前无活动 Run，launchd/listener PID 均为 8883；从运行中 label 参数解析实际 HARNESS_DB，并做 SQLite backup + quick_check 后才停服。新 PID 64681，release 与监听身份一致，详情及备份位置见 deployment.json。
- 浏览器从页面真实提交合成 pay-03：run_4de9d41dcc014e078b32949b087bce43，4 次模型/3 次工具、650 Token，成功；票据位于模型轮次 1/2/3。
- 浏览器显式选择真实豆包，同一份合成 pay-03：run_134be1e3af0545b9ab4c498b728b0117，4 次模型/8 次工具、11508 Token，成功；工具分布在模型轮次 1/2/3，完成三轮工具往返，说明该路径上 Ark 接受了平台改写的工具 ID。没有自动重试。
- 两个 Run 的 receipt 状态序列、调用数与预算一致，预留归零；产物 sha256/长度逐个核验；页面四个计划步骤、四槽位表格及正文可见，pageerror=0。截图已人工查看，见 live/*.png。运行目录残留 0。完整摘要见 live/live.json。
- 结果业务状态仍为 partial；这里只验收协议和发布链路，不把一个样本称为模型准确率。没有语义正确性、跨进程回放、OS 沙箱或生产多租户验收。8765/132 未操作。
- 回滚：只停经 label/listener PID 核实的 8876，代码切回 5a83d38 后用 deploy/start_dsh_session.py 启动。保留 DB，不恢复旧调用、不自动重发 Provider。若需要恢复备份，须独立判断丢失新写入的风险，不能把它当作普通代码回滚。
- 部署后 mymacclaude 独立只读 GET/进程检查：ad957fb、PID 64681、真实 Run 成功、4 次模型/8 次工具/第1–3轮往返/11508 Token/预留0 均核实。它没有重复真实模型请求；预签发未使用 model failed 仍按已登记 Low 解释。
