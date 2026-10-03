# 本轮验证缺口与修复队列

基线 b51dce6；以下为 HA-0053 实测发现，不是对全部功能的最终审计结论。

## 已复现的缺陷

| ID | 问题 | 证据/影响 | 后续验收 |
|---|---|---|---|
| RUNTIME-01 | cancelled Exchange 再进入 stream 会调用 Provider 并变为 succeeded | 合成 Adapter 探针：cancel 后 provider_calls=1，final=succeeded/done；当前真实模型 gate 关闭，因此未发生真实外发 | 取消前/中/后、Generator close、断线、终态不可覆写、无 assistant 持久化 |
| RUNTIME-02 | 同一 Exchange 并发 stream 可以调用两次 Provider | 同一 ID 两个 gather，合成 Adapter.calls=2，计数字段仍只能到 1 | 原子执行认领、重复消费者不触发调用、不取消原执行；重启清理 |
| OPENAPI-01 | Agent Lab 的 Schema 被 Agent Runtime 同名定义覆盖 | 合法 Lab model 请求 HTTP 201，使用已发布 OpenAPI 校验却报 provider_profile_id pattern 错误 | 命名隔离、合法/非法实例与 Schema 同集校验、所有引用可解析 |
| TEST-01 | Checkpoint 重启用例竞争 | 初始全量 1 failed：预期 failed 却为 running；测试启动后台 Worker 后又手动 execute | 注入阶段关闭 Worker；重启阶段只由真实 Worker 执行；已修复，定向及全量通过 |

以上 Runtime 探针为临时 SQLite + 合成 transport，外部网络调用 0；不是生产
事故或真实模型测试。修复不能只隐藏问题/修改声明，必须补行为回归。

## 接口基线

148 个方法/路径组合（包含 HEAD、页面、静态 mount），22 类功能。
观察器全量运行：307 passed、16 skipped，122 个入口被测试请求命中，26 个
未观察到。明细在 `harness/evidence/HA-0053/http-observations.json`。

其中多数缺口是 list/read API：Lab/Runtime 列表、Memory Bank 列表、研究列表、
Team Session/Agent 列表、资源读取及 Replan 列表；另外 Workspace 创建/成员
授予的 HTTP 路径尚无观测（内部方法测试不等于端点测试）。全部需补 HTTP
正反例。122 个 observed 仍需逐项检查断言，不能直接标为验收通过。

## 尚未完成的端到端验证

- 所有公开请求/响应与实际 OpenAPI/静态 OpenAPI/JSON Schema 一致性。
- 列表/详情的正反例、跨 scope、错误码、幂等、预算和状态变更后的读行为。
- 各浏览器入口与前缀、两端真实容器、修复后的重启/回滚与双端部署。
- 参考文档对照与过时 Current/README/历史 evidence 的声明纠正。
- 真实模型/外发/网盘账号相关能力须保留 gate；没做过的真实验证保持缺失。
- mymacclaude 对固定修复提交的独立 review。

本文件是开放问题清单，不意味着用上述样本替代用户的全部接口/功能目标。
