# HA-0048 验收证据

状态：running（契约与实例校验已提交，控制器实现和业务评测仍待后续步骤）。

- 设计：`docs/harness/ITERATIVE_RETRIEVAL.md`、`docs/decisions/ADR-0041-iterative-retrieval-control.md`
- 机器契约：`specs/v1/retrieval-state.schema.json`
- 当前边界：只允许 M1/M2-A/M3-A 的确定性本地路径；`source_trust_mode=unavailable`；外部/语义检索默认关闭。
- 机器校验：`harness/tasks.json`、`harness/task.schema.json`、`specs/v1/retrieval-state.schema.json` 通过 JSON Schema 校验；`git diff --check` 通过。
- 回归：`bash harness/verify.sh` 通过（283 passed, 12 skipped, 1 warning）；新增 1 个合法实例与 5 个负例；现有 M2-A/M3-A 评测仍明确不代表语义/vector/RRF/rerank。
- 待补：实现控制器、确定性评测数字、review 复审。
