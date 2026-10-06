# HA-0094：平台反馈在上下文压力下不被省略

依据：jikesummary《上下文分诊》（错误/失败信息为 P0，超预算也要保留）、《语义压缩》（错误不能被压缩吞掉）。

问题：`dsh_context.assemble` 超预算时按“最旧优先”把工具结果替换为存根，存根提示“需要原文时用 read_clause 重新读取”。但 submit_findings 的拒绝反馈（错误码、hint）不是证据块，read_clause 取不回来；一旦被省略，模型只知道“未通过”，看不到为什么。可信状态消息也只写“第N次，未通过”，不带错误码。

修复：
1. 不含证据块的工具结果（平台反馈）永不存根；若因此仍超预算，沿用既有的 DSH_CONTEXT_OVER_BUDGET 拒绝发送（fail-closed）。
2. 可信状态消息在最后一次提交未通过时附平台错误码（只含固定码，不含文档正文）。

验证（定向）：
- 新增 tests/test_dsh_context_feedback.py 3 passed：8000 窗口下拒绝反馈逐字保留、证据仍按旧规则存根；状态行带错误码，通过时不带；真实 DSH SDK + 合成 Provider 跑一次被拒提交后，下一次模型请求的状态消息含实际错误码。
- 反例：两个源文件恢复为基线 50f6f41 时 3 failed；单点突变 M1（反馈也存根）1 failed，M2（不传错误码）1 failed。
- DSH 相关 7 个测试文件 138 passed。

边界：准确范围是“不含证据块的工具结果不被存根”，不是所有平台反馈都不被存根。同时含 matches 和 NO_NEW_EVIDENCE notice 的结果仍可能被整体存根，notice 随之消失（mymaccodex 复审 Low，已复现）。反馈本身超过窗口时仍按 DSH_CONTEXT_OVER_BUDGET 拒绝发送，输入不被修改。没有改变估算方法或预算，没有引入摘要模型。复审：codex Approved（3dd3ca2，限代码与离线行为）。完整 verify 由 mymaccodex 统一安排。
