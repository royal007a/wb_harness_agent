# HA-0031：实现 Memory Context M2-A

状态：已完成。2026-09-20 已通过 209 项全量 opt-in 回归、合成评测、本机 launchd 和公网 systemd/nginx 发布验证；部署细节与一次已恢复的运行环境事故见 `harness/evidence/HA-0031/`。

## Objective

在不启用模型、外网或自动会话摄取的前提下，将 M1 的显式 Source/Fact 扩展为结构化 Fact Capsule、SQLite FTS5 候选目录和按 evidence ID 精确详情召回，并用合成评测证明摘要/细节与删除边界。

## Scope

1. 先落 ADR-0027、独立机器契约、API 与文档，明确 M2-A 与完整 M2 的差异。
2. 增加可重建 FTS5 Fact 索引、可选有界 detail、`:context` 与 `:recall-details`；确保最近轮只在请求中传递，原始 Source 正文不返回。
3. 覆盖 Bank 隔离、时间/生命周期、详情精确性、敏感输入、索引重建和合成评测；完成本机与远端双环境部署、备份、健康/端点验证与无密 Evidence。

## Non-goals

- 不自动读取飞书、Agent Runtime Session、文件、PDF、代码库、网盘或互联网。
- 不调用 embedding、模型、RRF/rerank、Reflect、外部 Hindsight 服务，也不把 FTS5 写成语义检索。
- 不开放多用户身份、Product Task/Run 绑定或向模型发送 Context/Detail。

## Acceptance

- 每个 Capsule summary 与 Detail 都能回到活跃、有效、同 Bank 的 Fact/Source；近期 turns 不持久化，原始 Source 内容不输出。
- FTS5 索引能从 Canonical Fact 重建；supersede/retract/delete/过期与跨 Bank 在 Context/Detail 路径均安全处理。
- 合成评测与 L2/L3 安全、重启、部署检查通过；本机和 `118.196.123.132` 均部署/验证，默认模型与外部能力维持关闭。
