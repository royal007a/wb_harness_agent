# HA-0114（候选，待审）：只读决策路径投影 GET /api/local/dsh/runs/{id}/trace

依据：jikesummary《为 Agent 引入 Tracing 复盘失败决策路径》（Run → Turn → LLM/Tool 树，用 duration 与参数定位问题）、《Agent 全链路监控》（Trace 只追加、Score 不改原记录）。可观测性摘要：现在只有扁平事件，复盘一次失败要手工按序号拼。

实现：`backend/dsh_trace.py` 纯函数，从持久事件按 `dsh.context.assembled` 切轮。每轮包括：上下文估算、模型耗时与用量（HA-0097）、本轮工具动作（含软错误码 HA-0099）与提交校验结果、本轮结束后的计划状态，以及停止原因。另外输出版本摘要（HA-0113）和终态（failed_step/failure_point，HA-0095）。所有字段白名单拷贝，不读产物、不读文档、不写库；复用 HA-0087 的全历史分页读取。

验证（定向）：tests/test_dsh_trace.py 2 passed（真实 DSH SDK + 合成 Provider 三轮：编造编号、检索、被拒提交、重读后提交；GET 前后 total_changes 不变；轮号连续；软错误码与检索命中数在第一轮；被拒提交只含码；每轮有整数耗时；投影里没有合同正文或标记文本；未知 Run 404）。突变：去掉 error_code 白名单 1 failed；不填模型信息 1 failed。运行时与计划历史回归通过。

边界：投影不是请求重建（与 codex 第五批结论一致）；没有前端视图。
