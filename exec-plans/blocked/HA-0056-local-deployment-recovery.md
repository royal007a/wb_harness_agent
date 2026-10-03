# HA-0056 有界 launchd 发布恢复

ce490c5 已获 mymacclaude 独立 **Approved（代码部分）**：45 passed，
额外 40 余 mock 场景；非阻塞 Low 见 acceptance.md。真实发布未执行，
本机拓扑选择与先本机后132验收仍阻塞；批准不等于部署完成。

2026-10-04 二次复审返工完成待复核（基线 0f5d6a7）：增加慢退出 20/50 秒、PID 复用、
观察命令耗尽窗口和恢复中断反例；修复已识别旧进程的恢复等待，等待/命令截止时间
按规格调整，补 Program 校验与停机阶段事实。45 项定向、全量 390 passed /
16 skipped 通过，旧脚本 10 个行为反例失败。固定提交后再交独立复审，
不执行真实 bootout/bootstrap，不将模拟结果称为双环境已恢复。

上一轮复审记录：预检、身份绑定和结构化错误，29项纯故障注入通过，
全量374 passed/16 skipped。新preflight在本机第一步就安全拒绝Background，
没有停服务或激活。实际发布仍需兼容调用会话，user域备选不在本次自动实施范围。
代码验证不等于部署恢复。

来源：HA-0055 本机 bootstrap/自动回退 exit 5，需要手动恢复。
规格：specs/testing/LOCAL_DEPLOYMENT_RECOVERY.md。

1. 临时目录故障注入复现旧脚本在暂态 5 和未验证回退上的缺陷。
2. 加有限重试、健康检查、失败回执；不扩大部署权限或声称代码/DB 回滚。
3. 定向、全量验证；固定提交后先本机再 132 发布。
4. Evidence 记录真实发布与模拟边界，交 mymacclaude 独立 review。

2026-10-03 17:16 UTC：步骤 1–2、冻结全量验证通过；步骤 3 发布被本机
GUI domain 不可用阻塞。gui/501 返回 125，8765 离线；132 保持 1840639。
待用户重新登录 weberzhao 图形会话，不绕过先本机后远端约束，也不擅自
切换到 system/root daemon。参见 HA-0056 acceptance.md 的失败与复跑证据。

独立 review 更正（2026-10-04）：上段“待用户重新登录”不是充分恢复条件。
调用方 managername=Background 可能仍无法操作 gui 域；reviewer 实测 user/501
配合 LimitLoadToSessionType=[Aqua,Background] 可用。该备选尚未在本项目采用。
exit 5 也可能是会话类型不匹配或已加载。先修 bootout 前预检、端口释放与
进程/发布身份绑定、结构化错误和恢复回执，不能只依靠重试；结论 Changes Requested。
