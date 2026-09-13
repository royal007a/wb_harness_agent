# HA-0013 本地意图契约、槽位澄清与规则路由

状态：completed。用户于 2026-09-13 明确授权实施本地意图最小闭环。

已完成：

1. 建立 `intent-contract@1` 与 `analysis_goal`/`resource_id` 槽位 Schema。
2. 用 `rules@1` 确定性识别本地 CSV 分析、返回缺资源澄清或拒识；无模型调用。
3. 将本地简化任务入口接入预检。预检无状态、不创建 Task；准备就绪后仍需用户显式提交。
4. 在工作台增加“预检分析意图”结果展示，保持用户内容安全渲染。
5. 添加固定评测集、评分器、API/故障/浏览器回归和无密 Evidence。

非目标保持不变：真实模型、向量/RAG、长期记忆、动态 few-shot、自动选引擎、外部数据访问和严格 Task API 的隐式改写均未实现。

Evidence：`harness/evidence/HA-0013/manifest.json`、`evaluation-results.json`、`all-tests.xml`、`browser.json`、`acceptance.md`。
