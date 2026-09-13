# HA-0024：本地 Agent Lab（Provider / Agent / Session / SSE）准备切片

状态：completed（2026-09-13）。依据 ADR-0021 和六份用户提供的课程 PDF，已完成可验证但无模型调用的本地准备切片。

## 目标

通过独立的配置与对话数据面，验证以下闭环：Provider/Model/Agent Profile 建模 → Agent 选择 → Session 创建 → POST SSE `delta/done` → 消息持久化、取消和刷新恢复。所有回复必须标明为本地确定性演示。

## 不变量与非目标

- Product Task/Run/Replan 控制闭环不变；聊天不能读写其数据。
- SQLite、API、前端、事件和 Evidence 不保存 API key、Token、凭证引用或原始 Prompt 以外的秘密。
- 不进行 DNS、HTTP、模型、Provider、SDK、工具、MCP、脚本或网络调用。
- 不实现 Markdown/HTML 富文本渲染；消息按纯文本安全显示。

## 分步执行与验收

1. **规格与边界**：新增 ADR、机器 Schema、阅读总结，更新 API/架构/安全/质量/技术债和任务状态。
   - 验收：Schema 能解析，文档链接有效，明确 `model_calls=0`。
2. **持久数据与业务服务**：实现受严格字段校验的 Profile、Session、Message、幂等 exchange；配置引用和 Session 归属校验。
   - 验收：单元测试覆盖未知字段、禁用引用、跨 Session、重复幂等键和内容冲突。
3. **HTTP/SSE**：实现本地 API、POST SSE 格式、断连检测和稳定错误码；增加 OpenAPI 描述。
   - 验收：集成测试确认 `delta → done`、保存顺序、模型/网络调用为零。
4. **浏览器 Agent Lab**：以结构→行为→细节实现配置表单和聊天时间线；使用 `fetch` 流、AbortController、`textContent` 和窄屏样式。
   - 验收：Playwright 创建配置、发送消息、见到逐块回复、刷新后保留历史，截图保留为 Evidence。
5. **验证、部署、归档**：全量回归、schema/link/security checks、launchd 重启与健康检查；写入 Evidence，归档计划并更新状态。
   - 验收：质量门禁通过；本机 `127.0.0.1:8765` 可用；不扩大真实引擎状态。

## 完成记录

- 规格、阅读总结、ADR、OpenAPI、执行 SOP、SQLite 受限数据面和 Agent Lab 前端均已落地。
- `sh harness/verify.sh`：155 passed，11 skipped，0 failure/error；`tests/browser_agent_lab.py`：9 项浏览器检查通过，0 页面错误。
- launchd 已重启；`/api/v1/health` 与 `/api/local/agent-lab/runtime` 均已验证，后者所有调用计数为 0。
- Evidence：`harness/evidence/HA-0024/manifest.json`、`all-tests.xml`、`browser-agent-lab.json`、桌面/移动截图与 `acceptance.md`。
