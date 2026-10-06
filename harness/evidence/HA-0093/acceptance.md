# HA-0093：凭据样式检测统一为单一定义

问题：`backend/` 有 5 份各自维护的凭据正则（agent_runtime、agent_lab、team_security、external_skills、memory）。agent_runtime 与 agent_lab 两份缺 `password`，DSH 建 Run 时用的 `reject_sensitive` 正是 agent_runtime 这份：`password=...` 的文档会被接受并进入 Run、发给 Provider。Team/Memory/外部 Skill 则会拒绝。来源：jikesummary 安全护栏（拦截管道/合同敏感信息多层护栏）关于“同一规则在所有入口一致”的要求，及 claude 复审 3036543 时实测。

修复：新增 `backend/sensitive_patterns.py` 的 `CREDENTIAL_SHAPE`，五个模块的 `SENSITIVE_INPUT` 都引用同一对象；规则取原有最严格版本（含 password），未新增身份证/手机号等会误杀合同正文的规则。

验证（定向，不是全量门禁）：
- 新测试 `tests/test_sensitive_patterns.py` 20 passed：五模块同一对象、`backend/` 中不再有私有副本、8 种凭据样式命中、5 种合同正文（含“密码由甲方另行通知”、passwordless）不误判、DSH 建 Run 遇 `password=` 返回 422 且不落库不回显。
- 反例：把 agent_runtime.py 恢复为基线 09caeca 版本，3 failed / 17 passed（共享对象、无私有副本、DSH 拒绝 password 三项失败）。
- 受影响模块的既有测试：agent_runtime/agent_lab/team_*/memory*/external_skill* 共 786 passed / 5 skipped。

边界：只统一凭据样式；不做 PII 脱敏或拦截（会破坏逐字引文校验并误杀合同）。完整 verify 由 mymaccodex 统一安排。
