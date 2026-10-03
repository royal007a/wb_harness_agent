# HA-0056 有界 launchd 发布恢复

来源：HA-0055 本机 bootstrap/自动回退 exit 5，需要手动恢复。
规格：specs/testing/LOCAL_DEPLOYMENT_RECOVERY.md。

1. 临时目录故障注入复现旧脚本在暂态 5 和未验证回退上的缺陷。
2. 加有限重试、健康检查、失败回执；不扩大部署权限或声称代码/DB 回滚。
3. 定向、全量验证；固定提交后先本机再 132 发布。
4. Evidence 记录真实发布与模拟边界，交 mymacclaude 独立 review。
