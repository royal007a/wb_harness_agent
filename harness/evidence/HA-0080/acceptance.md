# HA-0080 证据：真实豆包跑合成付款合同 + 两处平台规则修正

用户 2026-10-06 明确要求“用真实豆包跑几份合成合同”。Provider：doubao-seed-2.1-lite（Ark coding/v3）；凭据仅通过 Keychain 引用 `HARNESS_DSH_CREDENTIAL_REF` 解析，未打印、未落盘。临时库与临时目录，不经过 8876/8765/132。

## 第一轮（修正前，提交 ab386fa 代码）

5 份：2 成功；`pay-09` `DSH_NO_PROGRESS`；`pay-13`、`pay-17` 首次调用 `DSH_PROVIDER_INVALID`。诊断（仅抓取合成合同的响应形状）：

1. 豆包一轮并行发出 5 个 `read_clause`，平台单次响应工具调用上限 4（HA-0077 设定）把整次响应判为无效。该次请求已发送但用量无法结算，账本按设计冻结预留（`reserved_after=1280000`），不冒充零消耗。
2. 豆包先搜索、再逐条完整读取搜索命中；HA-0079 把“读取已在搜索中返回过的块”计为无新证据，4 次后误停。

## 修正

- `MAX_TOOL_CALLS_PER_RESPONSE = 8`（单 Run 工具执行仍 ≤16）。
- 进展判定：`read_clause` 对某块的**首次**读取算新证据；重复读取已读块、搜索未返回新块才算无进展。原“同一动作连续两次无新证据即停”保持。
- 回归：`test_real_pattern_search_then_first_reads_of_all_hits_not_stopped`、`test_real_pattern_five_parallel_reads_in_one_turn_accepted`、`test_rereading_already_read_clauses_still_stops`。

## 第二轮（修正后，`real_runs.json`）

| 案例 | 族 | 结果 | 模型调用 | Token | 期限数值 | 例外 |
|---|---|---|---|---|---|---|
| pay-01 | 例外在第二页 | succeeded / partial | 6 | 13859 | 与标注一致（20天） | 报出 clause-5 |
| pay-05 | 例外在第一页 | succeeded / partial | 4 | 10632 | 一致（45天） | 报出 clause-2 |
| pay-09 | 无例外 | succeeded / partial | 5 | 11738 | 一致（45天） | unknown，无误报 |
| pay-13 | 隐含例外 | succeeded / partial | 3 | 7048 | 一致（90天） | 报出 clause-5（“延后结算”，平台词表识别不到，模型自己找到） |
| pay-17 | 工作日单位 | succeeded / partial | 3 | 7754 | 一致（20个工作日） | unknown，无误报 |

合计 21 次模型调用、51031 Token。全部为 `partial`：冲突槽位为 unknown，或模型自述了缺口。

## 观察到的边界（真实模型）

- pay-13 的期限结论附带“以人民币结算、银行转账”，该内容不在其引用的 clause-1 中；因不含数值/主体，机械校验放行。说明机械校验只约束数值、单位、主体和引文来源，结论中的其他事实仍需人工复核。
- 5 份样本、单次运行，不构成质量统计；未覆盖错误数值的真实诱发。

## 验证

全量 `verify.sh` exit 0：1669 passed / 22 skipped（`verify.log`）。
