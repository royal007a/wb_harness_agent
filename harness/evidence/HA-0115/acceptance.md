# HA-0115（候选，待审）：两类“未读”缺口同时上报

依据：jikesummary《扇出聚合》（先盘点缺席，再下结论；缺什么要如实列出）；检索摘要指出 `dsh_findings.verify` 用 elif，只要有未读例外候选就不再报告未读付款块。

修复：EXCEPTION_CANDIDATES_UNREAD 与 PAYMENT_CLAUSES_UNREAD 独立判断；例外候选本身也是付款块，不在付款缺口里重复列出。business_status 规则不变（有平台缺口即 partial）。

验证：tests/test_dsh_gap_reporting.py 2 passed；基线 1 failed。付款/HA-0079 探针/评分/计划/注入/主体绑定 128 passed。评分器只看数值与例外，不受影响。
