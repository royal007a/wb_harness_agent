# HarnessAgent 进度摘要

> 本文件应由 `harness/tasks.json` 与 `harness/state.json` 自动生成。当前尚无生成器，因此仅作为初始快照；任务状态仍以 JSON 为准。

- 当前阶段：`awaiting_baidu_netdisk_oauth_configuration`
- 是否开始实现：是，用户于 2026-09-12 授权本地初版前后端和部署
- 当前任务：`HA-0011` 百度网盘真实 OAuth 连通验证；本机无回显配置助手已完成，等待用户运行并自行授权
- 最近完成：`HA-0010` 百度网盘官方 OAuth 本地连接底座，计划与 Evidence 位于 `exec-plans/completed/HA-0010-baidu-netdisk-oauth.md`、`harness/evidence/HA-0010/`
- 已记录证据：三份 PDF 阅读（18 页、SHA-256、官方交叉核验）；L0 静态验证；Claude 独立复审 Approved；Git 基线 `4aacf5a3c2eb`
- Backlog：`HA-0002` 核心契约与模拟纵向切片；`HA-0003` Smolagents/远程沙箱探针；`HA-0004` Smolagents P0 适配器；`HA-0005` Doubao 图片理解探针
- 当前阻塞：`HA-0008` 仍等待本项目批准的模型端点、模型 ID、凭证引用和预算；HA-0011 已完成配置助手和 107 项测试，仍需用户创建百度开放平台应用、登记精确本机回调、在本机输入凭证并由本人授权
- 当前发布：`0.1.0-local`，http://127.0.0.1:8765
- 最后检查点：98 项完整测试通过；百度网盘 OAuth 页面 5 项及原工作台 12 项浏览器检查通过；launchd 更新后持久数据可访问，连接入口 `/connectors/baidu-netdisk`。OAuth 数据面关闭，Claude SDK 0.2.152 仅做离线配置验证，真实模型路由未开启。

本地切片按 ADR-0009/0010/0011 独立授权完成。真实 VM 与脚本模型驱动的 Smolagents SDK 探针已有证据；完整 P0 冻结、生产沙箱、真实 LLM/Claude SubAgent 与 Doubao 能力验收仍未完成，不将固定函数编排等同于完整 Agent。
