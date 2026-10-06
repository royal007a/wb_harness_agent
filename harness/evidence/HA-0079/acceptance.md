# HA-0079 证据：付款条件结构化验收、覆盖缺口与无进展停止

基线 `2503b10`（DSH 分支 `1a4d4ce` + 前六讲报告）。分支 `dsh/minefield-ab-20261006`，worktree `~/code/ai/harnessagent-dsh-ab`。实现者 mymacclaude，待 mymaccodex 只读 review。

## 已执行

| 项 | 结果 | 证据层级 |
|---|---|---|
| 新增 `tests/test_dsh_payment_findings.py` | 32 项：纯校验 21 项 + 官方 DSH SDK 子进程/合成 Provider 11 项 | 离线 |
| DSH 定向（新增 + test_dsh_runtime + test_dsh_adversarial） | 独立重跑 122 passed（`targeted.xml`）；此前一次与全量并发跑时 `test_sigkill_then_recover_removes_registered_document_residue` 因负载超时（等待事件 20s），单独重跑两次通过；以 `verify.log` 的独立全量结果为准 | 离线 |
| 全量 `harness/verify.sh`（独立运行） | exit 0：1646 passed / 22 skipped，其余评测与 node/diff 检查通过（`verify.log`） | 离线 |
| 定向突变 6 项 | 全部被测试捕获，见 `mutations.json` | 离线 |
| 固定评测 `harness/dsh_payment_eval.py` | 20 例，见 `eval.json` | 离线（合成 Provider） |
| 旧探针（`harness/evidence/course-first-six-2026-10-06/probes.py`，描述 1a4d4ce 局限）在新代码上 | 探针1仍通过（`free` 模板按设计保留草稿边界）；探针2失败（现在第3次调用即 `DSH_NO_PROGRESS`）；探针3失败（搜索结果格式变为分页对象，其断言不再成立）。对应新验收见下 | 离线 |

## 三个旧探针的新验收

1. **30→300**：`test_old_probe1_inverted_300_days_cannot_become_verified_result`——`payment_terms` 下错误数值被 `CLAIM_VALUE_NOT_IN_QUOTE` 拒绝 3 次后 `DSH_FINDINGS_INVALID`，无产物，事件不含“300天”；4 次模型调用都记在同一账本。`test_correction_after_rejection_publishes_checked_findings`：纠正为 30 天后发布。`free` 模板仍会发布引用合法的错误草稿（`test_free_template_keeps_previous_draft_boundary`），这是保留的边界，不是修复。
2. **重复读取**：`test_old_probe2_inverted_repeated_read_stops_early`——从 8 次硬上限变为第 3 次调用 `DSH_NO_PROGRESS`；`test_legitimate_search_then_reads_are_not_stopped`：先搜索再读 3 个已返回块不被误停；`test_four_consecutive_actions_without_new_evidence_stop`：不同查询但持续无新证据也会停。
3. **第四条例外**：`test_correction_after_rejection_publishes_checked_findings` 中翻页（`offset=3`）读到 clause-4 并作为例外发布；`test_old_probe3_inverted_fourth_exception_is_found_or_reported` 中模型不翻页、两次提交，平台先提示 `COVERAGE_GAP`，再接受但记 `EXCEPTION_CANDIDATES_UNREAD: clause-4`，`business_status=partial`。

## 结构化负例（纯校验 + SDK 集成）

未知带引文、冲突仅一个来源、缺槽位、无证据的 supported、非列表引文、多余字段、超长 gaps、引文被改写（30日 vs 30天）、未读/编造/跨文档 clause 编号（`QUOTE_CLAUSE_NOT_READ`）、天→工作日、三十→三百、主体替换（丙方）、读到例外候选却报 unknown（`EXCEPTION_CANDIDATE_NOT_REPORTED`）。错误代码不回显模型文本；事件不含结论和引文（`test_findings_text_never_enters_events`）。

## 预算与优先级

- 纠正是正常模型调用：走同一 `budgeted_model_call`、同一 8 次上限、截止时间和取消检查。
- `test_budget_exhaustion_wins_over_correction_loop`：先实测每次预留，再把上限设成第 3 次（纠正）无法预留，结果 `BUSINESS_TOKEN_BUDGET_EXHAUSTED`、只发 2 次、预留归零、无产物。
- 未调用 `adaptive_retrieval.retrieval_control`：它的六维预算任一为 0 即停止，而 DSH 的 `max_cost_minor=0` 表示“不批准额外付费”、rerank 未启用，都不是“耗尽”。不传假预算值；无进展停止只看证据进展，预算只由持久账本裁决（ADR-0079）。
- 模型请求本 Run 未提供的工具（如 `free` 下的 `submit_findings`）立即 `DSH_TOOL_POLICY`。

## 固定评测（`eval.json`）

20 个合成公开文本案例，5 族各 4 例：例外在第一页之后、例外在第一页内、无例外、隐含例外（不含词表用词）、工作日单位。`cases.json` 只有文档、问题和脚本参数；`labels.json`（真值、例外编号、是否隐含）在全部运行结束后才读取，不进入运行时或脚本 Provider。脚本 Provider 是标签盲的“朴素”策略：只看第一页搜索结果，只有平台提示时才补读；奇数号案例故意把数值乘以 10。

| 指标 | 结果 |
|---|---|
| 误报数值未被发布 | 10/10 |
| 正确数值被发布（待人工复核） | 10/10 |
| 词表可见例外被呈现（作为结论或平台缺口） | 4/4 |
| 无例外文档无误报候选 | 4/4 |
| 隐含例外被平台词表识别 | **0/2**（已知局限） |

只证明平台控制逻辑；样本少，不报显著性；真实模型合规率与分析质量未验证。

## not_evidence

未调用真实 Provider、未部署（8765/8876/132 均未动）、未改上游 DSH Loop；不证明语义支持（否定词翻转检不出，见 `test_negation_change_is_not_mechanically_detectable`）；不是法律或投资结论验收；上下文组装器（报告 C）未实现。
