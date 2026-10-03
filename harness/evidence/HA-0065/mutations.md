# HA-0065 定向突变

独立worktree基于0ee58a0，覆盖当前候选的app/store/openapi投影、源/静态契约和两份
测试文件；不修改主仓库或正式服务。每次只改一个点，执行新测试对应selector，保存
mutation-NAME.xml/log，再反向apply_patch恢复；每个文件恢复后的SHA均与突变前相同。
所有运行exit1，XML errors=0；没有导入/收集错误。

| NAME | 只改变的约束 | tests / failed |
|---|---|---|
| dynamic_422 | responses['422']=envelope改为pass | 1 / 1 |
| task_required | task_detail.required移除runs | 1 / 1 |
| retryable_const | const:false改为type:boolean，专跑True反例 | 1 / 1 |
| utc_checker | 时间检查器直接return True | 14 / 10 |
| http_upper | Query移除le，Store防御保留 | 8 / 4 |
| store_guard | 移除Store.events的类型/范围检查 | 8 / 8 |
| next_cursor_upper | 源next_cursor删除maximum | 1 / 1 |
| event_upper | 源Event.sequence删除maximum | 1 / 1 |
| run_upper | 源Run.latest_sequence删除maximum | 1 / 1 |
| static_upper | 静态after删除maximum | 7 / 2 |

UTC的4个合法例仍通过；HTTP保留Store防御后仍422，但新增检查发现不该调用的
Store.events被调用；Store缺防御时有未拒绝、OverflowError和非法类型绑定错误。
这是10个特定突变都被杀死，不是随机全库mutation score或全部边界覆盖证明。
Event/Artifact引用前缀的12个反例另在旧版验收中失败，不混称为本表突变。
