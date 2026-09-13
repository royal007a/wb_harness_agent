# HA-0019 验收记录

日期：2026-09-13；范围：ADR-0018 的本地固定统计 Checkpoint / Restore 产品纵向切片。

## 已验证

1. `LocalAnalyticsAdapter@1.1.0` 只在 `resource.inspect` 后形成版本化的确定性统计状态；状态由 SQLite 追加保存，未保存原始 CSV、目标正文、Prompt、密钥或模型上下文。
2. `POST /api/local/runs/{id}:restore` 只接受空 JSON 和幂等键。它仅允许 `failed`/`expired` 源 Run 创建新的同 Task 恢复 Run；原 Run 保持终态，`cancelled`/`succeeded` 不能恢复。
3. 恢复前重验 Checkpoint/状态、源 Run、Task、资源 SHA-256、适配器 descriptor、有效权限与剩余预算。故障注入覆盖资源、Task、权限、适配器、预算、状态与取消；状态会与固定输入重新回算，预算会与源 Run/已消费步骤交叉校验。因此即使篡改者重算 Checkpoint 自身摘要，也无法创建扩容或错误状态的恢复 Run；每种失败均未创建新 Run 或产物。
4. 回归验证恢复 Run 只运行固定发布路径，不再次发送 `resource.inspect`；它重新回算已保存统计状态，不匹配时拒绝，不能用新结果掩盖篡改。
5. 临时本地部署的 Chromium 验收确认：可恢复失败 Run 显示“从检查点恢复”，点击后创建新 Run、发布三个产物，且 UI 明确保留旧 Run。

## 命令与证据

```sh
.venv/bin/python -m pytest --junitxml=harness/evidence/HA-0019/all-tests.xml -q
HARNESS_BROWSER_EVIDENCE="$PWD/harness/evidence/HA-0019" \
  .venv/bin/python tests/browser_checkpoint_restore.py
.venv/bin/python harness/checkpoint_restore_evidence.py
sh harness/verify.sh
```

结果以 `all-tests.xml`、`browser-checkpoint-restore.json`、两张浏览器截图和 `manifest.json` 为准。

## 仍不在范围

- 通用 Plan/Replan、TCC API、候选 Plan 编辑或跨引擎恢复；
- 模型、网络、任意代码、远程沙箱、外部副作用或权限扩大；
- 生产级灾备、身份隔离、多租户授权或恢复 SLO。
