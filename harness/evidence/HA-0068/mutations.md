# HA-0068 定向突变

在独立868f4b3 worktree覆盖候选生产文件及最终新测试，不改主树。
每次只改一处，pytest结束后反向apply_patch，逐文件cmp与主树一致。
具体替换、selector及退出码见mutations.json，原始结果见mutation-*.xml/log。

| 突变 | 选择用例数 | 行为失败 | errors |
|---|---:|---:|---:|
| 删掉提交前重查 | 3 | 2 | 0 |
| 删掉迟到事件重查 | 2 | 1 | 0 |
| 删掉Gate事务内当前状态检查 | 4 | 3 | 0 |
| Gate回放前再拦终态 | 2 | 2 | 0 |
| next_seq改回全Run最新序号 | 1 | 1 | 0 |
| 最新Gate倒序改正序 | 1 | 1 | 0 |
| 只删HTTP查询上界，Store保护保留 | 5 | 2 | 0 |
| runtime_enabled放宽boolean | 1 | 1 | 0 |
| 事件页Schema上限放宽501 | 1 | 1 | 0 |

9/9被杀死不等于全库mutation score。没有覆盖每一个Schema关键字、每条竞态，
也不是实际并发Provider或正式服务取消证据。
