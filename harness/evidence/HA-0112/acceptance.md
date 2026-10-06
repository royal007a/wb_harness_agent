# HA-0112（候选，待审）：插件声明的工具契约与平台检查之间的漂移测试

依据：jikesummary《护栏三明治》（契约漂移：守卫与工具必须出自同一份版本化契约）、上下文《信息散落》（重复存放的知识都要当成依赖管理）。安全与上下文摘要指出：工具参数在 platform-plugin.mjs 与 Python 校验各写一份，provider 只比对工具名；CONTEXT_WINDOW=64000 在两处各写一份，没有一致性断言。

改动：`platform-plugin.mjs` 的 `TOOLS` 改为 export（只读引用，行为不变）；search_document 描述补充 HA-0110 的归一化语义。新增 tests/test_dsh_contract_drift.py：用 node 加载固定插件导出声明；断言：
- submit_findings 的必填参数等于 `dsh_findings.SLOTS`，可选参数只有 gaps；
- 描述中的“at most N”等于 `SEARCH_PAGE`，`contextWindow` 等于 `CONTEXT_WINDOW`；
- 直接驱动平台网关（绕过 SDK 自身的 schema 校验）：只带必填参数、带全部声明参数都被接受；多一个未声明参数或缺任一必填参数都返回 DSH_TOOL_INPUT 且不执行工具。

验证：4 passed；突变：插件窗口改成 128000、插件新增参数、Python 接受额外参数，各 1 failed。对抗/运行时/票据 113 passed。

发现：经真实 SDK 发送的未声明或缺失参数，在 SDK 侧就被拒、不会到达平台。所以平台检查只能用直接驱动网关的方式测试，测试中已注明。
