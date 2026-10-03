# HA-0055 验证（进行中）

初始 HEAD 4eddb8d，两端应用 912faca。原问题通过 HA-0054 真实截图和
frontend/agent-runtime.js 的 chooseSession/renderMessages 调用确认。
本轮先增加浏览器稳定断言，未完成前不宣称错误状态 UI 已验收。

## 旧实现反例

- `ui-before.xml`：旧 UI，queued/streaming/cancelled 三种持久状态的浏览器断言
  全失败；另有 1 个 fixture 启动 10s 超时，不计作产品缺陷证据。
- 将临时服务启动等待上限设为 30s 后，单独重跑 `-k failed_send`，见
  `failed-send-before.xml`：1 failed / 7 deselected。发送按钮恢复后，页面只有
  用户消息，没有 MODEL_RUNTIME_DISABLED。这是稳定状态断言，不是瞬时文本。
- 测试使用临时 SQLite、本机 HTTP 和真实 Chromium；无外部 Provider 请求。

## 修复范围

Exchange 状态以独立系统卡呈现，按 user_message_id 关联；未关联记录仍展示。
发送固定原 Session；详情使用选择代次，旧请求不能覆盖新选择。流内容标为
未持久化，断流/停止显示不能冒充成功或服务端已取消。测试增加合成成功、
XSS、慢详情、旧流完成、孤立状态、提前 EOF 和浏览器 abort。

保持真实模型门禁关闭；本任务不代表 OpenAPI 或所有接口验收完成。

`ui-first-fix.xml` 保留首轮修复验证：10 passed / 1 failed。失败来自测试在
Playwright 所在事件循环嵌套 asyncio.run，不是浏览器断言；已改为通过临时
HTTP 服务发送合成成功请求。`backend-regression.xml` 为 80 passed，参数化
testcase 名中的原始夹具已机械替换为 SHA-256，避免保存超长输入；结果未改动。
提前 EOF 测试覆盖浏览器消费平台 SSE，不等于 Provider 上游协议的 EOF 验收；
后者仍在 GAPS.md 中待单独验证。

## 发布前通过

- `verify.log`：完整 verify.sh exit 0；pytest 337 passed / 16 skipped，检索/
  记忆/Team 等既有评测、准入校验、前端语法和 diff 检查通过。这一全量采集
  包含最初 11 项 UI 测试；追加中间态测试未修改应用代码。
- `ui-after.xml`：最终 UI 文件 12 passed。额外用本机 HTTP 的合成 Adapter
  暂停在真实 SSE 中段，确认预览标记、数据库只有 user、页面无 assistant；
  释放后才出现唯一持久 assistant 和 succeeded 卡。
- 接口清单 148 方法/路径、22 功能分组仍一致。
- 当前待办：本机→132 发布及真实部署浏览器截图；mymacclaude 独立 review。
