# HA-0080 部署记录：合并到 DSH 分支并重启 8876

日期 2026-10-06。用户要求合并到 mymaccodex 的 DSH 分支；mymaccodex 确认未使用 8876，同意重启，并要求保留发布前版本、只停该 label 的进程。

- 合并：`dsh/local-runtime-20261005` 从 `2503b10` fast-forward 到 `cbb3e9e`（无合并提交）。
- 发布前：8876 由 launchd label `local.harnessagent.dsh-session` 的 PID 80103 监听（lsof 与 `launchctl list` 一致），运行提交 `c43df5b`。8765 当时无监听，未触碰；132 未触碰。
- 停止：只执行 `launchctl remove local.harnessagent.dsh-session`，确认 8876 不再监听。
- 启动：`deploy/start_dsh_session.py`（干净工作区、端口空闲、Keychain 引用可读；argv/env 不含密钥）。新 PID 74901 监听 8876；`/api/local/dsh/runtime` 返回 release `cbb3e9e`，`workspace_recovery` 全 0；`/dsh` 页面 200，新前端含模板选择。
- 部署后真实验证：经 8876 HTTP 接口提交合成合同 pay-03（`payment_terms`、`real_provider`），`run_a2e4f357ed544575a2bf0fac6ae329c6` succeeded，3 次模型调用、7521 Token、预留归零；发布正文为平台根据校验结果生成的文本，期限 30 天与标注一致，例外 clause-5 被报告。该 Run 保存在 `.local/dsh.db`，可在页面历史中查看。
- 回滚：在 `~/code/ai/harnessagent-dsh` 执行 `launchctl remove local.harnessagent.dsh-session`，`git checkout c43df5b`（或将分支重置回 `2503b10`），再运行 `deploy/start_dsh_session.py`。数据库向后兼容：新增字段只在新 Run 的任务变量和新产物中出现。
- 不承诺开机自启；会话级 launchctl submit，重启电脑后需在已授权会话重新运行启动脚本。
