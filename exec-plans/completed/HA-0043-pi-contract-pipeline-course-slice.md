# HA-0043：Pi 合同审查课程 17–22 的首条可验证纵切片

状态：已完成（2026-09-24）

## 目标

把课程 17–22 的解析、分类、分块和外部安全护栏原则落为本项目的无模型、无网络合同 PDF 预览契约；同时固定资料摘要、测试和双环境部署证据。

## 范围与非目标

- 范围：Public PDF 注册资源的解析、确定性分类、条款分块、敏感信息计数、结构化响应、幂等和 OpenAPI。
- 非目标：真实 Pi/Provider、联网搜索、法律结论、真实风险 Skill、ChatPanel、TUI 和身份认证。

## 验收

- `specs/v1/pi-contract-pipeline.schema.json` 校验请求与响应。
- `/api/local/pi-contract-pipeline/preview` 可运行且重复请求结果一致。
- 敏感命中只返回类型/数量，状态转为 `needs_human`，不返回原值。
- `PYTHONPATH=. .venv/bin/pytest` 全量回归通过；本机与 `118.196.123.132` 均重启并健康检查。
- Provider/模型、外部网络和真实 Agent 仍保持关闭，并在 Evidence 中明确记录。
