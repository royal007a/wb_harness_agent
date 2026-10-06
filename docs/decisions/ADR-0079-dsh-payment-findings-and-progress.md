# ADR-0079：DSH 付款条件核对的结构化结果、覆盖缺口与无进展停止

状态：已接受（实现于分支 `dsh/minefield-ab-20261006`）；日期：2026-10-06。

## 背景

前六讲对照报告（`docs/research/PRODUCTION_AGENT_FIRST_SIX_2026_10_06.md`，2503b10）的三个探针表明：引用合法但数值错误（30→300）仍会发布；同一读取要耗到 8 次硬上限才停；搜索只返回前三项时遗漏第四条例外。报告 A/B 建议在不改上游 DSH Loop、不扩大工具池、不新增预算体系的前提下补齐业务验收与进展控制。

## 决定

1. 请求新增可选 `template`（`free` 默认 / `payment_terms`）。`free` 行为不变：仍是引用合法即发布的人工复核草稿。
2. `payment_terms` 运行额外提供 `submit_findings` 工具（工具集合按 Run 冻结在 `requested_permissions.allow_tools`，Provider 侧和执行侧都按该集合校验，模型请求未提供的工具即 `DSH_TOOL_POLICY`）。
3. 平台纯函数校验（`backend/dsh_findings.py`）：四个槽位 term/trigger/exception/conflict 必填；`supported` 需 1–3 条引文，引文必须逐字出现在**本轮实际返回给模型**的证据块中；结论中的数值+单位（含简单中文数字）和甲乙方必须出现在引文中；`conflicting` 需两个不同证据块；`unknown` 不得带引文。错误只返回固定代码，不回显模型文本。
4. 平台用字面词表计算付款相关和例外候选证据块：例外候选未读时，第一次提交返回 `COVERAGE_GAP` 要求补读；再次提交接受但记 `EXCEPTION_CANDIDATES_UNREAD`；读过例外候选却报 unknown 记 `EXCEPTION_CANDIDATE_NOT_REPORTED`。业务状态为 `mechanically_checked` / `partial` / `conflicting`，均需人工复核。
5. 校验失败最多纠正 2 次，第 3 次失败 `DSH_FINDINGS_INVALID`；没有通过校验的结果则 `DSH_FINDINGS_MISSING`，不发布。每次纠正都是一次正常模型调用，走同一 `budgeted_model_call`、同一 8 次上限、同一截止时间和取消检查；预算耗尽、取消优先于纠正。
6. 搜索结果分页：每页 3 条，返回 `total/offset/next_offset/truncated`，可用 `offset` 继续。
7. 进展由平台判断：动作指纹 = 工具 + 规范化参数 + 资源；新证据 = 模型此前未收到的证据块。同一动作连续两次无新证据，或任意 4 个连续动作无新证据，即 `DSH_NO_PROGRESS` 停止；在停止前一次以 `notice` 提示。合法的“先搜索、再逐条读取”不会触发（最多 3 个连续无新证据）。
8. 发布在同一事务内追加 `dsh-findings.json` 产物（Schema `findings`），事件只记固定类别、计数和业务状态，不含结论或引文。

## 不做 / 边界

- 不调用 `adaptive_retrieval.retrieval_control`：它要求六维预算且任一维为 0 即停止，而 DSH 的 `max_cost_minor=0` 表示“不批准额外付费”、rerank 未启用，都不是“已耗尽”。不传假预算值绕过它；本切片的无进展停止是独立的、只看证据进展的规则，预算仍只由持久账本裁决。
- 引文存在、数值一致只是机械检查，不证明结论被证据支持（例如否定词翻转无法检出，见测试 `test_negation_change_is_not_mechanically_detectable`）。
- 例外候选来自字面词表，隐含例外（如“延后结算”“再行处理”）会漏检，评测中 0/2。
- 合成 Provider 只证明控制逻辑；真实模型产出合规结构的比例未验证。
