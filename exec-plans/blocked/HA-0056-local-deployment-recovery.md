# HA-0056 有界 launchd 发布恢复

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
