# HarnessAgent 进度摘要

> 本文件应由 `harness/tasks.json` 与 `harness/state.json` 自动生成。当前尚无生成器，因此仅作为初始快照；任务状态仍以 JSON 为准。

- 当前阶段：`intent_contract_routing_verified`
- 是否开始实现：是，用户于 2026-09-12 授权本地初版前后端和部署
- 当前任务：无；本地 Intent Contract 已验收，当前规则仅支持 CSV 分析
- 最近完成：`HA-0013` 本地 Intent Contract、槽位澄清、规则路由/拒识和固定评测；证据位于 `harness/evidence/HA-0013/`
- 已记录证据：三份 PDF 阅读（18 页、SHA-256、官方交叉核验）；L0 静态验证；Claude 独立复审 Approved；Git 基线 `4aacf5a3c2eb`
- Backlog：`HA-0002` 核心契约与模拟纵向切片；`HA-0003` Smolagents/远程沙箱探针；`HA-0004` Smolagents P0 适配器；`HA-0005` Doubao 图片理解探针
- 当前阻塞：`HA-0008` 仍等待本项目批准的模型端点、模型 ID、凭证引用和预算；TD-020 未关闭，百度网盘文件数据面与内容解析仍不开放；TD-021 未关闭，意图模型、向量/RAG 和长期记忆尚未进入运行时。
- 当前发布：`0.1.0-local`，http://127.0.0.1:8765
- 最后检查点：130 项完整测试通过；`intent-contract@1` 的 7 条固定评测样例全通过，预检/显式提交浏览器流程无错误。百度网盘 OAuth 的真实一次 refresh 仅访问官方 token endpoint，且无文件 API 调用/无密 Evidence；分享链接 Skill 仅交接官方客户端。连接入口 `/connectors/baidu-netdisk`。OAuth 数据面关闭，Claude SDK 0.2.152 仅做离线配置验证，真实模型路由未开启。

本地切片按 ADR-0009/0010/0011 独立授权完成。真实 VM 与脚本模型驱动的 Smolagents SDK 探针已有证据；完整 P0 冻结、生产沙箱、真实 LLM/Claude SubAgent 与 Doubao 能力验收仍未完成，不将固定函数编排等同于完整 Agent。
