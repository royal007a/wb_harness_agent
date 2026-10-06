# ADR-0082：付款核对计划投影、提交历史与延迟清理（A1 / C / D）

状态：已实现（分支 `dsh/local-runtime-20261005`）；日期 2026-10-06。依据：`docs/research/PRODUCTION_AGENT_L07_L10_2026_10_06.md`（42fa228，mymaccodex Approved），课程《生产级 Agent 排雷实战》第 08 讲（计划数据化）、第 07 讲思考题、第 10 讲。A2 证据续跑与 B 调用身份/重放防护**未实现**，仍为设计。

## A1 计划可视化与状态投影
- `backend/dsh_plan.py`：`payment_terms` 的平台计划 `dsh-plan@1`，四步 S1 定位付款相关块、S2 读取例外候选、S3 提交并通过校验、S4 发布。
- 状态每次由平台事实**重新投影**（已返回给模型的块、最后一次提交的校验状态、是否发布），不是单向推进：S3 通过后若后续提交被拒，回到 `blocked`（带固定错误码），S4 回到 `pending`。S1/S2 的 `partial` 不阻塞 S3/S4；`done` 只表示词表候选已返回，不代表语义证据找全。
- 第一次模型请求前写入 `dsh.plan.created`；之后状态变化写 `dsh.plan.step`（只含步骤号、状态、证据块编号、错误码）。可信状态消息附计划进度，并声明模型不能修改。`run.failed` 附 `failed_step`；`run.succeeded` 附 `plan_status`。Run 详情接口返回投影后的计划，页面显示执行计划面板。模型文本无法改变任何步骤状态。

## C 提交历史
- 每次 `submit_findings` 记录序号、是否通过、固定错误码、内容摘要哈希、被哪一次提交取代；`dsh.findings.checked` 事件对通过与被拒都带序号和摘要哈希。
- 发布的 `dsh-findings.json` 增加 `submissions` 历史（不含未通过版本的正文）。未通过版本不保存为任何“通过”的产物；人工复原入口未实现。

## D 延迟清理（DSH-CLEANUP-01）
- 启动恢复后若仍有 `pending` 的登记目录，按 `HARNESS_DSH_CLEANUP_RETRY_SECONDS`（默认 10 秒）间隔最多重试 6 次，规则与启动清理完全相同（只处理登记项、租约释放且进程组不存在才删、不杀恢复出的 PID）。结果计入 `workspace_recovery`（含 `retries`）。
