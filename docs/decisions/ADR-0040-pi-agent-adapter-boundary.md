# ADR-0040：Pi Agent Runtime 作为合同审查可选适配器

状态：Proposed  
日期：2026-09-23

## 背景

Pi-mono 将 Provider/Model、Agent Loop、业务 Harness 和终端 UI 分层，并以事件驱动方式暴露模型、工具和 turn 生命周期。它适合透明、可替换的 TypeScript Agent Runtime，但没有内置平台级文件、进程、网络、凭证和业务权限边界。直接把 Pi 嵌入当前 Python 服务会把运行时、控制面和安全责任混在一起。

## 决策

将 Pi 作为 P2 合同审查场景的可选 Adapter，采用 TypeScript sidecar：

- `pi-ai` 处理 Provider/Model/Context；
- `pi-agent-core` 处理 AgentLoop、turn、工具调用、steering/followUp 和事件；
- `pi-coding-agent` 只作为后续可选的高层 Session/扩展层；
- `pi-tui` 只用于本地 UI，不进入服务端 Worker；
- HarnessAgent 控制 Task/Run、Tool Runtime、Policy、Budget、Sandbox、Evidence、Artifact、Gate、Checkpoint 和审计；
- 所有 Pi 事件必须映射为平台 Engine Events，`agent_end` 不得直接宣称 `run.succeeded`。

## 后果

正面：源码可审计，Provider 可替换，事件可观测，Pi 版本升级与平台契约隔离，合同审查可先以离线假模型验证。

代价：需要 Node/TypeScript sidecar 生命周期、跨进程协议、版本锁定、事件背压、取消传递和双语言测试；Pi 的 Session/Compaction 不能自动成为平台长期状态；工具和安全边界需要重复映射与验收。

## 非目标

- 不在本 ADR 中安装 Pi、启用真实 Provider 或实现合同审查业务；
- 不授予 Pi 直接文件、进程、网络、Keychain 或宿主路径权限；
- 不把 Pi 的内置 UI、扩展或 prompt 当作授权系统；
- 不替换现有固定 CSV 适配器、Claude 准入路径或 Memory Plane。

## 准入条件

先完成 P2-Pi-0 离线事件探针和 P2-Pi-1 合同模拟纵切；只有事件映射、取消、预算、权限、引用、schema、审计和回滚证据齐全后，才可申请 P2-Pi-2 真实模型准入。
