# HA-0079：DSH 付款条件结构化验收、覆盖缺口与无进展停止

分支 `dsh/minefield-ab-20261006`（worktree `~/code/ai/harnessagent-dsh-ab`），基线 2503b10。依据：前六讲对照报告 A/B（报告已获 mymacclaude Approved）；决策见 ADR-0079。

1. 规格：`specs/v1/dsh-runtime.schema.json` 增加 `request.template` 与 `findings`。
2. 实现：`backend/dsh_findings.py`（纯校验）、`backend/dsh_runtime.py`（工具集合、分页、进展、提交校验、发布事务）、`backend/dsh_provider.py`（按 Run 工具集合、按工具参数上限）、`dsh-adapter/platform-plugin.mjs` / `bridge.mjs` / `adapters/dsh.py`（工具按 Run 注册）、前端模板与结果表。
3. 验证：`tests/test_dsh_payment_findings.py`（三个旧探针反向验收 + 结构化负例 + 预算/事件边界）、既有 DSH 测试、定向突变、固定评测 `harness/dsh_payment_eval.py`。
4. 交 mymaccodex 只读 review。不部署 8876/8765/132，不调用真实 Provider。

## 完成记录（2026-10-06）

- ebcb8fa 首版被 mymaccodex Changes Requested（4 Medium + 2 Low，附独立反例）；ff72a21 修订后获 Approved，批准限于代码与离线验证。
- 复审方独立复跑四个 DSH 测试文件 142 passed；全量 1666 passed、20 例评测和突变为作者侧证据。
- 未合并、未部署、未调用真实 Provider；报告 C 未实施。证据见 harness/evidence/HA-0079/acceptance.md。
