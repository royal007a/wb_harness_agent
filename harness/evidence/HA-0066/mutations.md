# HA-0066 定向突变

独立e6e1fb9 worktree覆盖本轮候选的app/openapi投影、core/memory源合同、静态文档
及最终新增测试。每次仅改一个点，测试后反向apply_patch恢复，cmp与主仓库一致。
没有操作主仓库业务代码、正式DB或服务。全部exit1，XML errors=0。

| NAME | 突变 | tests / failed |
|---|---|---|
| binding | 去掉7项动态响应绑定 | 7 / 7 |
| bank_list_runtime | 列表runtime不再必填 | 1 / 1 |
| research_engine | demo列表允许任意engine | 3 / 1 |
| research_parent | demo列表不再限制parent_run_id | 3 / 1 |
| semantic_runtime | 放宽semantic.runtime_enabled恒false | 10 / 10 |
| keyword_engine | ready=true时不再要求FTS engine | 10 / 5 |
| counts_minimum | facts计数允许负数 | 1 / 1 |
| static_detail | Bank详情静态响应错绑单个Bank | 1 / 1 |

每项selector保留在对应JUnit/log的测试名称中。其余引擎或FTS失败分支仍通过
是预期；本表是8个定向反例，不是全库突变覆盖率或全部安全边界验证。
