# HA-0020 验收记录

状态：passed（2026-09-13）。依据 ADR-0019 的受限授权，完成本地固定分析器的确定性 Plan/Replan TCC 纵向切片。

## 已验证

- 只接受真实 `ARTIFACT_PUBLICATION_FAILED` 的失败 Event Evidence；调用方不能提交目标、候选节点、资源、权限、预算、Prompt 或代码，且 Replan 查询不回显目标或原始 CSV。
- 提案同时持久化基线与唯一恢复 PlanRevision；恢复路径固定为 `checkpoint.verify → artifact.publish → run.final_answer`。
- Try 不创建 Run 或调用工具；Confirm 用计划、Checkpoint、Task、资源、适配器、有效权限与剩余预算摘要比较并交换，且每个 Checkpoint 只可物化一个恢复 Run；Cancel 只终结未确认 Attempt。
- Try 后绑定漂移会使 Confirm 过期且不创建 Run；取消后可创建新 Attempt；Try 状态跨重启保持并可后续 Confirm；8 个不同 Confirm 幂等键并发时仍只物化一个恢复 Run。非空 Try/Cancel 请求被拒绝，且 Try/Cancel 不会调用 adapter。
- 浏览器临时部署覆盖创建方案、Try、Confirm、新 Run、源 Run 不变、产物、checkpoint 验证与不重复 `resource.inspect`。

## 验证命令

```sh
.venv/bin/python -m pytest --junitxml=harness/evidence/HA-0020/all-tests.xml -q
HARNESS_BROWSER_EVIDENCE="$PWD/harness/evidence/HA-0020" \
  .venv/bin/python tests/browser_replan_tcc.py
.venv/bin/python harness/replan_tcc_evidence.py
sh harness/verify.sh
```

结果：JUnit 162 个用例（151 passed、11 skipped），0 failure / 0 error；浏览器 9/9 检查通过。另有静态/运行时 OpenAPI Replan 路径一致性测试。模型、适配器网络和任意代码调用均为 0。

## 不等同的能力

这不是通用 Agent Replan：没有模型、网络、任意代码、计划编辑、自动根因推断、非白名单失败、跨 Task/资源/引擎恢复，且不取消已确认 Attempt。
