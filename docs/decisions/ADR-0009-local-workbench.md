# ADR-0009：本地工作台初版

状态：Accepted（本地原型范围）；日期：2026-09-12。

用户在话题中要求“给个设计给出初版 harness 代码，前后端”，并两次明确“实现”。本次授权解除纯文档阶段限制，允许实现可演示的纵向切片。

采用 Python FastAPI + SQLite + 原生 JavaScript/CSS。前端与 API 同源，绑定 loopback；单进程单 Worker，SQLite 事务原子保存 Run 状态、事件和产物。固定本地 workspace/project，不宣称多租户认证。来源：[FastAPI StaticFiles](https://fastapi.tiangolo.com/tutorial/static-files/)、[SQLite Python API](https://docs.python.org/3/library/sqlite3.html)。

第一版提供 CSV 上传、固定统计分析、Task/Run、事件游标、取消、重跑、报告、SVG、manifest 与工作台。使用显式 `engine_mock_analytics`；分析真实计算，意图仅记录，模型调用为零。未知引擎/模型/能力拒绝；模型生成代码、联网、视觉与长期记忆仍待后续能力探针。

运行时新增开发专用 `/api/local/tasks` 简化创建；`/api/v1/tasks` 继续验证既有 JSON Schema。本地配置仅支持固定 agent/profile。重启时 queued 继续领取，running 标记 failed/SERVER_RESTARTED，可创建新 Run；不假装恢复解释器。UI 每秒按游标拉取持久事件，不声明 SSE。

后果：容易启动和验收，部署规模限制为可信用户的本机。生产认证、远程隔离、完整 L3 独立审查尚未完成。该决定不批准剩余框架或 P2 记忆供应商。
