# HarnessAgent Pi Adapter Probe

这是 P2-Pi-0 的离线契约探针，不是生产合同审查运行时。

## 运行

```sh
npm ci
npm test
npm run probe
```

探针固定 `@earendil-works/pi-agent-core@0.87.1` 与 `@earendil-works/pi-ai@0.87.1`，使用 Pi 官方 Faux Provider，不读取 Keychain、不调用网络、不启用真实模型。它验证：

- Agent → turn → tool → tool result → next turn → proposed result 的事件映射；
- `evidence_locate` 工具在 Agent Loop 中执行，但由 `beforeToolCall` 做白名单校验；
- 未知 Pi 事件 fail-closed；
- 有界事件队列只丢弃可重建的 delta，终止/工具事件溢出则失败；
- `abort()` 产生终止的 `agent_end`，且没有外部调用。

真实 Provider、合同文件、平台 Tool Runtime、Python Adapter 和 Product Run 尚未接入。
