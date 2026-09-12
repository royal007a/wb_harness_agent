# HarnessAgent 进度摘要

> 本文件应由 `harness/tasks.json` 与 `harness/state.json` 自动生成。当前尚无生成器，因此仅作为初始快照；任务状态仍以 JSON 为准。

- 当前阶段：`local_orchestration_preview`
- 是否开始实现：是，用户于 2026-09-12 授权本地初版前后端和部署
- 当前任务：无正在执行任务；`HA-0009` 多专项 Child Run 本地切片已完成
- 最近计划：`exec-plans/completed/HA-0009-child-run-orchestration.md`
- 已记录证据：三份 PDF 阅读（18 页、SHA-256、官方交叉核验）；L0 静态验证；Claude 独立复审 Approved；Git 基线 `4aacf5a3c2eb`
- Backlog：`HA-0002` 核心契约与模拟纵向切片；`HA-0003` Smolagents/远程沙箱探针；`HA-0004` Smolagents P0 适配器；`HA-0005` Doubao 图片理解探针
- 当前阻塞：`HA-0008` 等待本项目批准的模型端点、模型 ID、凭证引用和预算
- 当前发布：`0.1.0-local`，http://127.0.0.1:8765
- 最后检查点：88 项全量测试、研究页面 9 项及原工作台 12 项浏览器检查通过；launchd 更新后持久数据可访问，研究入口 `/research`。Claude SDK 0.2.152 仅做离线配置验证，真实模型路由未开启。

本地切片按 ADR-0009/0010/0011 独立授权完成。真实 VM 与脚本模型驱动的 Smolagents SDK 探针已有证据；完整 P0 冻结、生产沙箱、真实 LLM/Claude SubAgent 与 Doubao 能力验收仍未完成，不将固定函数编排等同于完整 Agent。
