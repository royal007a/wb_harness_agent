# HA-0097 / HA-0098：调用耗时与 free 模板输出影子扫描

依据：jikesummary《在 Harness 层拦截 Token 与耗时》（只拦截 Generate 会漏掉工具耗时）、《Tracing 复盘失败决策路径》（duration_ms 决定从哪层优化）、《护栏三明治》（新规则先影子模式，计算误报后再决定是否阻断）、安全护栏摘要中“free 模板直接发布模型原文、无任何输出检查”的缺口。

HA-0097：`dsh.model.completed` 增加 `latency_ms`（monotonic，含平台预算/取消包装的完整等待）；`dsh.tool.completed` 增加 `latency_ms`（从网关进入 tool_call 到事件提交）。只记整数。
HA-0098：新模块 `backend/dsh_output_scan.py`（版本 dsh-output-scan@1），free 模板发布时在同一发布事务里写 `dsh.output.scanned`：四类计数（凭据样式——复用 HA-0093 的单一定义、注入标记——复用 HA-0096、手机号、身份证号），`mode: shadow`，不阻断、不打码；`run.succeeded` 带 `output_scan_flagged`。payment_terms 发布的是平台渲染文本，不扫描。

验证（定向）：tests/test_dsh_observability_ha0097.py 4 passed（模型等待 250ms → latency_ms≥250；工具耗时为整数；扫描只返回计数、长数字串中不误报手机号；free 产物与模型原文逐字相同、扫描事件在 run.succeeded 之前、事件中不含号码；付款模板不扫描）。突变：模型 latency 写死 0 → 1 failed；去掉扫描事件 → 1 failed。DSH 运行时/对抗/票据/退役/计划历史/付款共 172 passed。

边界：影子数据用于后续计算误报率，本项不改变发布内容；耗时不是 Trace 树，跨轮投影（只读 /trace）未做。
