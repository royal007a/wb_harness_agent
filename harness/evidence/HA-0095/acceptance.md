# HA-0095：失败点与最早未完成步骤分开

依据：jikesummary《Replan（下）：失败点不等于根因点》。HA-0082 的 `failed_step` 取“第一个非 done/not_applicable 的步骤”。S1 只是合法的 partial（不阻塞发布）时，S3 连续被拒导致 DSH_FINDINGS_INVALID，`failed_step` 仍报 S1，把排查引向错误位置。

修复（向后兼容）：`run.failed` 保留 `failed_step`（含义：最早未完成步骤），新增 `failure_point`：固定错误码映射（DSH_FINDINGS_MISSING/INVALID→S3）优先；否则取被 blocked 的步骤；否则退回最早未完成步骤。只用平台计划与固定错误码，不含正文。

验证（定向）：tests/test_dsh_failure_point.py 3 passed（纯函数顺序；真实 SDK + 合成 Provider：只读 clause-1 后反复错误提交 → failed_step=S1、failure_point=S3；只搜索不提交 → S1/S3）。HA-0082 计划测试与探针共 26 passed。突变：去掉错误码映射 2 failed；去掉 blocked 优先 1 failed。

边界：不是根因分析；未知错误码只退回最早未完成步骤。前端暂未展示 failure_point。
