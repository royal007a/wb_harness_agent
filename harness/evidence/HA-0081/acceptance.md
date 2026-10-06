# HA-0081 证据：上下文组装器、按轮进展判定、真实豆包回归

依据见 ADR-0081（Harness Agent 脚手架实战课第 17 讲 + DeepSeek Harness 一讲）。

| 项 | 结果 | 层级 |
|---|---|---|
| `tests/test_dsh_context.py` | 12 项：配对校验、可信状态、最旧优先省略、最新一轮保护、超预算拒发、注入不提权、确定性、DSH SDK 集成（省略后重读算进展、超预算零发送） | 离线 |
| 按轮进展回归 | `test_real_pattern_parallel_searches_in_one_turn_are_one_progressing_turn` 等；旧“重复读取”探针仍在第 3 次调用后停止（第 4 次请求前判定） | 离线 |
| 定向突变 | 去掉按轮判定、省略、超预算拒发、配对校验（两处）、最新一轮保护、重读豁免：全部被捕获（其中 3 项首轮存活，补用例后捕获） | 离线 |
| 合成评测（新增 2 万字以内长合同 1 例，共 21 例） | `eval.json`：误报数值 10/10 不发布；正确数值 11/11 发布；词表例外 5/5 呈现；无例外 4/4 无误报；隐含例外 0/2 | 离线 |
| 全量 `verify.sh` | exit 0：1682 passed / 22 skipped（`verify.log`） | 离线 |
| 真实豆包 7 份短合同（`real_runs.json`） | 7/7 succeeded；期限数值 7/7 与标注一致；有例外的 5 份全部报出（含 2 份隐含例外）；无例外 2 份无误报；33 次调用、87131 Token | 真实 |
| 真实豆包长合同 18320 字（`real_long.json`） | succeeded；期限 35 天一致；例外 clause-13 报出；最大估算 18795 < 预算 44800，未触发省略；4 次调用、26979 Token | 真实 |
| 真实压测（窗口 16000，`real_long_forced_stub.json`） | 失败且未发布：`DSH_CONTEXT_OVER_BUDGET`（最新一轮 6 个大块超预算）。改为保留摘录前的一次压测为 `DSH_TOOL_LIMIT`（反复重搜）。记录为边界，不调参掩盖 | 真实 |

真实运行均为合成公开文本、临时库；凭据经 Keychain 引用解析，未打印、未落盘。样本少、单次运行，不作质量统计。

## 部署后追加（873a5f7 → 本提交）

873a5f7 部署到 8876 后，真实长合同两次失败：一次单轮工具调用超过 8 个（`DSH_PROVIDER_INVALID`，已发送但用量无法结算，账本按设计冻结预留），一次超过单 Run 16 次工具上限（`DSH_TOOL_LIMIT`）。修正：单次响应工具调用上限 16，单 Run 工具执行上限 32（模型调用仍 ≤8）；`test_sdk_exact_tool_call_cap` 改为 32/33 边界。

长合同连跑 3 次（`real_long_rep1..3.json`）：3/3 succeeded，期限 35 天与 clause-13 例外每次正确；工具调用 10/20/9 次（20 次那次在旧上限下必然失败）；最大上下文估算 25985/41925/24517，均未超过 44800，未触发省略；Token 64603/92983/51308。全量 `verify.sh` 重跑 exit 0：1682 passed / 22 skipped。

## 复审修订（343a3b3 → 本提交）

mymaccodex 对 343a3b3 给出 2 Medium + 2 Low，附 3 个独立反例，原样收为 `tests/test_dsh_ha0081_review_probes.py`，现全部通过。

| 问题 | 修订 | 回归/突变 |
|---|---|---|
| M 被省略的旧副本持续制造“新进展” | 组装器区分“某历史副本被省略”（`stubbed_clause_ids`）与“当前没有任何完整副本被发送”（`invisible_clause_ids`）；运行时重读豁免只用后者 | `test_full_current_copy_prevents_false_new_progress`；突变 D1（改回用 stubbed）被捕获 |
| M 字符估算被称作 Token 上界 | 降格为 `chars_heuristic@2`（含 ID 与每消息 8 的封装余量），ADR/文档明确不是 Token 计数、不是硬保证，花费由业务账本按真实 usage 结算 | 文档修订 |
| L 配对校验非严格 | 严格序列：同轮 ID 唯一；结果须紧随、每 ID 一条、不得被其他消息隔开 | 两条反例通过；突变 D2/D3 被捕获 |
| L “可重建”表述 | 明确只有摘要审计，完整请求重建未实现，不把正文写进事件 | ADR-0081 第 6 条与边界 |

DSH 六个测试文件 161 passed；全量 `verify.sh` exit 0：1685 passed / 22 skipped。未发真实请求（本修订不改变发送内容的结构，只改进展判定与校验）。

## 复审结论

73e7e25 获 mymaccodex Approved（限代码与离线验证）。其非阻塞建议已采纳：`estimate_after` 改为按实际发送的最终状态重算（`test_estimate_after_matches_what_is_sent`）。
