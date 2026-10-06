# HA-0113（候选，待审）：每个 Run 记录决策所用的版本摘要

依据：jikesummary《Agent 全链路监控》（Generation 要带 promptVersion，意图字段实时富集而不是事后补录）、《生成评审》（ReviewReceipt 记录 digest 与 critic/policy 版本）。可观测性摘要指出：只有 state/messages 摘要，release 只出现在 status()，事件里没有提示词、工具契约、校验器版本。

改动：在第一次模型请求之前写 `dsh.run.versions`：release、prompt_sha256（提示词含用户 objective，只记摘要）、工具名列表、contract_sha256（platform-plugin.mjs + controlled.patch.yml）、validator_sha256（dsh_findings.py）、plan_version。`run.succeeded` 附 release/validator_sha256/plan_version。dsh-findings.json 不加字段：codex 的 HA-0082 兼容探针要求新记录去掉 submissions 后仍能通过旧 Schema，加字段会破坏这一点（首版这样做了，探针失败后改到事件里）。

验证（定向）：tests/test_dsh_versions.py 2 passed（版本事件早于第一次上下文组装、不含 objective 原文、成功事件带版本且 findings 不带；objective 不同则 prompt 摘要不同，校验器与契约摘要相同）。突变：prompt 摘要写成常量 1 failed。付款/计划/计划历史/运行时/对抗/退役、HA-0082 探针、HA-0097 共 16+ 定向及 6 个回归文件通过（见提交说明）。

边界：摘要不能重建提示词；不改变运行行为。
