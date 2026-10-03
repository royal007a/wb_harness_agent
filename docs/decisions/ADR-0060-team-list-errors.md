# ADR-0060：按明确不可见原因过滤，故障保持失败

状态：fff8d75代码已获mymacclaude独立Approved；双部署仍阻塞。
源自 HA-0059 复审的既有 Medium，基线8a7e840。

Channel列表已限定过滤原因，但 Session/Task/Inbox/Recovery 及 Session Task
snapshot 使用 except Problem: continue，会把访问检查里的503变成200空列表。

决定：在 TeamFoundation 定义不可变 `(code,status)` 白名单，共用判定，不捕获
任意403/409，也不按错误文本分类。Task历史无绑定例外仅在检查Task时显式选择。
identity 校验是请求级前置条件；Recovery 也必须在扫描前检查。
不改变可见性授权、不降级故障、不扩大执行权。测试规格见
specs/testing/TEAM_LIST_FAILURES.md。

复审边界：非法status值（如None/ACTIVE/actve）仍被既有的非active判断隐藏，
未实现枚举损坏的STATE_CORRUPT检查；Channel列表仍使用原code-only过滤。
这些不属于本轮修复完成项，见specs/testing/GAPS.md。
