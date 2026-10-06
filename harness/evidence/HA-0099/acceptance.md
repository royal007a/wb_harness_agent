# HA-0099：格式正确但不存在的证据块编号改为有界的可纠正观察

依据：jikesummary《别把执行权交给概率：六大契约》（错误分红绿灯，可纠正的错误要带 hint 回给模型）、《操控循环》《四个子系统》（反馈要回到循环里，而不是直接终止）。

问题：模型一次编出 `clause-999`，`DSH_CLAUSE_NOT_FOUND` 就让整个 Run 失败，真实豆包额度白花，模型也没有改正机会。

修复：只对格式正确（`clause-[1-9][0-9]{0,5}`）但不存在的编号返回观察 `{matches: [], error: CLAUSE_NOT_FOUND, hint: 编号范围 + 先 search}`，计入工具次数和无进展判定（new_evidence=0），事件带 `error_code`。每 Run 最多 2 次，第 3 次仍然 `DSH_CLAUSE_NOT_FOUND` 失败。路径样式、前导零、大小写不符、未准入工具、多余参数、空查询等全部维持原来的硬失败（对抗测试新增 `clause-01`、`Clause-999` 两条）。

验证（定向）：tests/test_dsh_soft_tool_errors.py 3 passed（真实 DSH SDK + 合成 Provider：编造编号后拿到 hint，改为检索、提交，Run 成功，模型调用 4 次无隐藏重试；第 3 次编造失败；软错误不算进展）。test_dsh_adversarial 61 项（含新硬失败用例）通过。基线 3 failed；突变：去掉次数上限 1 failed，任意 ID 都软处理 3 failed。DSH 运行时相关 7 个文件 121 passed。

边界：不改变越权与格式错误的 fail-closed；不自动重试。
