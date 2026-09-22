# HA-0026 验收记录

## 交付内容

- ADR-0023、`research-agent-runtime@1` Schema 与三个第一方 instruction-only Skill。
- 独立 `engine_research_multi_agent_simulation`：父 Run 为每家公司创建财务、行业、风险三个 Child Run；每个 Child 固化 Agent / Skill / Tool / 预算快照。
- 受控两步 Action → Observation → Final 模拟循环：唯一工具为分配资源上的 `resource.inspect`，父级仅汇总独立回算通过的 Child artifact。
- `/research-agents` 页面、请求/详情 API、取消、重跑、部分失败和浏览器验收。

## 验收结果

- 全量回归：171 passed，11 skipped，0 failed / 0 errors。
- 浏览器：桌面、窄屏、三角色扇出、零外部调用、下载、重跑、风险资料缺失、事件、刷新全部通过；控制台错误为 0。
- 契约反例：Skill 摘要漂移、权限扩大和越界资源读取均被拒绝；最大并发为 3。
- 运行时事实：模型、Provider、网络和外部工具调用均为 0。

## 不可外推的边界

此项不实现 Claude Agent SDK 的实际 SubAgent，不读取财报 PDF，不调用 WebSearch/WebFetch/金融数据/模型，也不构成真实研报或投资建议。真实接入仍受 TD-017、TD-018、TD-019、TD-025、TD-026 与单独授权约束。
