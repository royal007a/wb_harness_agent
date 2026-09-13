# HA-0021 验收记录

状态：通过（2026-09-13）。ADR-0020 把固定产物构建失败组织为持久 Gap State，且不扩大 ADR-0019 的模型、网络、工具或恢复边界。

## 预期验证

- `ARTIFACT_PUBLICATION_FAILED` 在写入失败 Event 的同一提交中创建一次 `gap@1`，指向 `node_publish`、`evidence/core`、`artifact.publish`。
- 提案读取同一 open Gap；Try、Cancel、Try 后漂移与失败恢复都不解决它。
- 绑定恢复 Run 仅在产物校验、发布和最终回答成功后写 `gap.resolved`，并将源 Gap 改为 resolved。
- Gap/Attempt 响应不含目标、CSV 或 Prompt；浏览器路径展示 open Gap 提示与恢复后的事件。

## 实际证据

- `python -m pytest --junitxml=harness/evidence/HA-0021/all-tests.xml -q`：163 个用例，0 failure、0 error、11 个既有环境跳过（152 passed）。
- `HARNESS_BROWSER_EVIDENCE=... python tests/browser_replan_tcc.py`：Chromium 临时部署 10 项检查通过；包含 `gap_created_and_resolved`、`checkpoint_verified`、`no_reinspect`。
- `python harness/replan_gap_evidence.py`：通过，且记录模型调用、适配器网络调用和任意代码调用均为 0。
- 产物摘要、浏览器报告和三张截图见同目录的 `manifest.json`、`browser-replan-gap.json` 与 `replan-gap-*.png`。
