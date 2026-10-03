# HA-0054 Runtime 生命周期修复

来源：HA-0053 的 RUNTIME-01/02。规格：ADR-0054。

1. 先用临时 SQLite 和合成异步 Provider 锁住取消、重复执行、Session busy、
   断线、重启、输出/时间上限的正反例；记录旧代码失败。
2. 原子认领、终态保护与关闭 owner；HTTP wrapper 不拥有业务状态。
3. 定向 + Workbench + verify；全接口清单同步应用行号。
4. 固定提交，备份实际 DB，本机后 132 部署；健康、门禁、容器和适用页面验证。
5. 向 mymacclaude 交固定版本独立 review。OpenAPI 冲突另列原子任务，不隐藏。

非目标：启用模型、通用 Agent Loop、Skill/Product Run 桥接、身份体系、自动
重试 Provider。合成验证不是模型在线成功证据。

2026-10-04 mymacclaude Approved；双部署证据与 review 边界见 HA-0054 acceptance.md。
UI、OpenAPI、上游 EOF 等剩余问题单独跟踪，不因生命周期批准而一并视为通过。
