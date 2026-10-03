# HA-0057 Provider 流完整性

代码验证完成：旧版本4反例失败；协议56项，相关合计132 passed；完整 verify
446 passed/16 skipped。85fc7d3 已获独立 Approved；当前追加修复复审 Low（读取前
拒绝内容编码、原始字节流）：11个旧版行为反例失败；相关143项、全量457 passed/
16 skipped通过，追加补丁986ed1d也已独立Approved。实际发布被HA-0056本机调用拓扑
决定阻塞，仍须先本机后132。Evidence位于 harness/evidence/HA-0057/。

目标：修复 PROVIDER-01，协议失败不可持久化成功回答。范围限 Adapter、相关契约、
测试与证据；不改 HA-0056 发布返工、不启用模型、不实现 Product Run/Skill 桥接。

1. 固化 ADR-0057 / PROVIDER_STREAM 的窄协议与错误分类。
2. ce490c5 上以 MockTransport+临时 Store 重现 EOF 与 length 误发布。
3. 实现有界 SSE 解析与终止判定，补协议、Runtime、HTTP、重放/取消回归。
4. 全量验证、固定提交、请 mymacclaude 只读 review。
5. 待 HA-0056 本机调用拓扑决定与复审通过后，先本机再132部署；代码通过不是部署完成。
