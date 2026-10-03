# HA-0067 定向突变

独立临时 worktree 从 5429c62 创建，复制候选 app/openapi helper、三份 Pi Schema、
静态 OpenAPI 和最终新增测试。每次只改一处，用 apply_patch 修改及还原，
还原后与主仓库 cmp 一致；测试只用临时 DB。8/8 被行为断言杀死，errors=0。

公共命令：`.venv/bin/python -m pytest -q tests/test_pi_pipeline_http_contracts.py -k <selector>`。
XML/日志为本目录 mutation-<名称>.xml/log。

| 名称 | 放松/改变 | selector | 测试数 / 失败数 |
|---|---|---|---|
| stream_finding_shape | finding data 改任意 object | pdf_preview_finding | 2 / 2 |
| stream_done_calls | done.model_calls 改任意 integer | pdf_preview_finding | 2 / 2 |
| stream_heading | 去掉流 heading 的 chunk-N 约束 | pdf_preview_finding | 2 / 2 |
| preview_security_status | 删除 preview 外层状态与 security 状态关联 | pdf_preview_finding | 2 / 1 |
| guard_deny_reason | deny 允许空 reasons | guard_is_evaluation | 5 / 3 |
| admission_enabled | approved 分支允许 admission_enabled=false | runtime_admission | 7 / 1 |
| stream_key_limit | 动态流 key 上限错写 128 | idempotency_key_limits | 4 / 1 |
| stream_order | 实际流先 finding 再 preview | pdf_preview_finding | 2 / 2 |

最后一项首次补丁因误把 tuple 写成 list 上下文而未应用；更正上下文后才运行，
不把该 apply_patch 失败算作被测试杀死。所有 worktree 已清理。
这不是全库 mutation score，不证明其他分支没有测试缺口。
