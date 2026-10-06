# HA-0082 验收：付款核对计划投影、提交历史、延迟清理（A1/C/D）

依据：`docs/research/PRODUCTION_AGENT_L07_L10_2026_10_06.md`（42fa228，mymaccodex Approved）；ADR-0082。A2 证据续跑、B 调用身份/重放防护**未实现**。

## 实现
- A1：`backend/dsh_plan.py` 平台计划 `dsh-plan@1`（S1–S4），每次由平台事实重新投影；首次模型请求前写 `dsh.plan.created`，变化写 `dsh.plan.step`；可信状态消息带计划进度；`run.failed` 带 `failed_step`，`run.succeeded` 带 `plan_status`；详情接口与页面显示计划。
- C：每次提交记录序号、结果、错误码、内容摘要哈希、被谁取代；`dsh-findings.json` 带 `submissions`（无未通过版本正文）。
- D：启动后仍 pending 的登记目录按 10 秒 × 最多 6 次重试，规则与启动清理相同。
- 真实运行发现的问题：豆包单次输出完整结构化提交超过 45 秒，被报成笼统的 `DSH_GATEWAY_FAILED`。修复：Provider 响应上限 120 秒（仍受 Run 剩余时间约束），超时显式报 `DSH_PROVIDER_TIMEOUT`，用量未知、预留冻结、不自动重试。

## 验证
- 新测试 `tests/test_dsh_plan_ha0082.py` 10 项；`harness/verify.sh` 1696 passed / 22 skipped（`verify.log`）。
- 突变 7 个全部被抓（`mutations.json`；P7 首轮存活，加固测试后被抓）。
- 部署：见 `deployment.md`。真实豆包（`real_runs.json`）：
  - 148dc5b：3 份中 2 份成功；pay-09 在第 5 次模型请求等待 45 秒超时，`failed_step=S3`，用量未知、预留冻结。
  - bc9d3f7：pay-09 / pay-03 / pay-07 / long-01 共 4 份全部成功；计划首次可见时为 pending，结束时 S1–S4 均 done（pay-09 的 S2 为 not_applicable）；按标注核对，发布的付款期限数值 4/4 正确，例外条款 4/4 正确（pay-09 无例外，记 unknown）。

## 边界
- S1/S2 的 done 仅表示词表候选已返回给模型，不代表语义证据已找全。
- 4 份样本只能说明这次改动没有破坏主流程，不能作为准确率结论。

## 复审修订（mymaccodex 对 8d0c079 的 Changes Requested）
- M1：工具/提交事件与它引起的计划变化在**同一事务**写入（`event(kind, value, *extra)`），提交成功后才采用新的内存计划；`failed_step` 只基于已提交计划。三种复现（拒绝后计划写失败、拒绝与投影之间取消、通过审计写失败）和工具读取同类窗口均有测试。
- M2：`httpx.TimeoutException` 族与内置 `TimeoutError` 一起映射为 `DSH_PROVIDER_TIMEOUT`；先 `check()`，取消/Run 截止优先。
- Low：`plan.step` 带 `evidence_ids`；`Service.stop()` 取消清理定时器、运行根目录在恢复时固定；findings Schema 的 `submissions` 改为可选以兼容旧记录（新记录总是包含）。
- codex 10 个探针纳入 `tests/test_dsh_ha0082_review_probes.py`，全部通过；新增 3 项测试；verify 1709 passed / 22 skipped；6 个回退突变全部被抓（R2 首轮存活后补测试）。
