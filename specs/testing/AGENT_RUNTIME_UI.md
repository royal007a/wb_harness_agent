# Agent Runtime UI 状态测试规格（HA-0055）

对应 UI-RUNTIME-01；沿用 ADR-0054 和现有 Session detail API，不改后端契约。

## 必须成立

1. 持久消息和 Exchange 状态分别呈现。failed/cancelled/queued/streaming 不得
   伪装成 assistant 消息。succeeded 的真实 assistant 仅显示一次。
2. 每个 Exchange 状态绑定 user_message_id，显示状态、Exchange ID、已记录
   的尝试计数以及存在的 error_code；即使历史没有关联消息也不能静默丢弃。
3. SSE 终止后的自动回读、重新选择会话、刷新页面再选择，都能看到同一失败。
   测试必须等待发送按钮恢复再断言，不能仅等待瞬时 SSE error 出现。
4. 流中内容显式标为未持久化，直到 detail 返回 succeeded 才视为完成；
   异常断流不能显示成功。浏览器 abort 不等于服务端已经确认取消。
5. 异步详情按选择代次接纳。慢返回的 A 不能覆盖后来选择的 B；发送绑定开始
   时的 Session ID，结束时不能把用户从 B 强制切回 A。
6. 所有字段用 textContent 渲染；状态内容不能注入 HTML。390px 无横向溢出。
   必须检查消息列实际 left/right 均在视口内，scrollWidth 不超过 clientWidth；
   只检查 document.scrollWidth 会漏掉 overflow:hidden 隐藏的内部列裁切。
   多会话横向列表选择可能滚动外层容器，所以只检查 right 也不够。
7. 当前页面最多持有一个发送流（不是服务端全局单并发）。A 发送时 B 仍可浏览，
   但发送按钮禁用并解释原因；停止按钮只在选中 A 时可见，事件处理器也必须
   再检查所属 Session，隐藏按钮的程序触发不得取消 A。
8. 浏览器停止或异常断流后，对原会话 queued/streaming 做有界只读回查：
   最多 6 次、间隔 500ms、整次详情读取含网络共用 5 秒 deadline。实际详情
   确认 cancelled/failed/succeeded 才显示对应终态；超限保留最后已知状态和
   “尚未确认终态”提示，不能自己写 cancelled。切换选择会中止旧详情回查。
9. 传输提示按 Session 保存在当前页面内，重选同一 Session 不会擦掉；新的
   发送清除该 Session 的旧传输提示。它不是数据库状态，页面刷新不保留。

## 验证

- `tests/test_agent_runtime_ui.py`：临时本机 HTTP 服务 + 真实 Chromium + 临时
  SQLite。模型默认关闭；如需合成成功消息，只使用显式的内存 Adapter。
- `tests/browser_agent_runtime.py`：真实部署 root / 前缀，稳定失败状态断言，
  发送结束、重新选择、刷新后重新选择均保持可见。桌面/手机截图和 JS 错误。
- `tests/browser_smoke.py`、前端语法、全量 verify，以及本机→132 部署健康。
- Browser 环境缺失只能 skipped，不能冒充通过。外部 Provider 不自动开启。
