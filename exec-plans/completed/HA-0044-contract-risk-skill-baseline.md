# HA-0044：合同风险 Skill 的确定性基线

状态：已完成（2026-09-24）

课程 19 的第一步已实现为 `skills/contract-risk-review` 和
`POST /api/local/pi-contract-pipeline/review`：服务端消费
`pi-contract-pipeline-preview@1`，输出带资源/分块哈希引用的 `needs_human`
候选，不调用模型和网络，不给出法律结论。脚本、API 幂等和 Skill 边界均有
测试；真实 Provider、跨块模型复盘和法律审查仍需单独准入。
