# HA-0039 验收记录

状态：accepted（本地受限控制面）

## 结果

- `error-contract@1` 由服务端稳定目录派生 `retryable`、建议下一步与所需 Evidence；每个 Case 单独保存失败点、根因**假设**、回滚 Checkpoint 和 Replan 起点。
- Try 只创建候选，Confirm 重验 Task、Checkpoint、固定无工具权限快照、预算和输入摘要，Cancel 只写审计；模型/工具/自动恢复调用均为零。
- 连续失败或无可验证进展仅产生软 Reminder；turn、时间、候选、重复 operation 和取消会停止 Case，且不会扩权。
- Confirm 或“重试成功”不能自动交付：只有相同 Team Task 的 Handoff 加 Gate `pass` 后 Case 才能 `resolved`。

## 证据

- 定向 `tests/test_recovery_loop_guard.py`：6 passed。
- 完整回归：231 passed、12 skipped、0 failed；见 `all-tests.xml`。
- 合成评测：Error Contract、四位置、零执行、Reminder/硬停止和 Handoff/Gate 回接均为 1.0；见 `recovery-loop-guard-evaluation.json`。
- 本机 launchd 与公网 systemd/nginx 均完成 SQLite 备份、重启、health、runtime 和 OpenAPI 检查；远端 staging/pip/nginx 检查通过，未认证公网入口仍为 401。细节见 `deployment.json`。

## 不代表

真实 Agent/工具恢复、真实 Checkpoint restore 或取消、外部副作用补偿、身份授权和动态权限审批仍未实现；TD-030 保持开放。
