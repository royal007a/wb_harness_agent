# 8876 发布前只读预检

日期：2026-10-07。候选 `09cb07befddb31f62292831ba31e149ff755678a`；**未发布**。本记录只描述检查当时的状态，不能替代实际停服前再次核对。

## 已观察

- `/api/local/dsh/runtime` 报告旧 release `ad957fb888789eccc1150d0ea0df643cce8047c9`。
- `local.harnessagent.dsh-session` 的 PID 为 64681；8876 唯一监听 PID 同为 64681。
- live worktree `harnessagent-dsh` 在 `5939e5d`，`git status --short` 为空；它是候选的祖先，可以 fast-forward，无须重写历史。
- workspace_recovery 的 cleaned、pending、retained、retries 均为 0。
- 只读 Run 列表共 24 项：20 succeeded、4 failed，活动 Run 为 0。路由通过 `store.listing('runs')` 读取全部行，不是只看第一页。没有读取或复制任务正文。
- 当前服务已安装 DSH；模型调用上限 8、工具调用上限 32；真实模式开关仍为 true。本次没有修改开关或调用模型。

## 候选与已验证快照

候选的运行代码、测试及根验证脚本与第七轮通过的 `1936d9c` 一致；候选后加的是文档/证据。第七轮为 1852 passed / 22 skipped，完整 verify exit 0，见 `verify-seventh.md`。HA-0090 最终结构关联修订包含在该快照中；HA-0093 以后候选代码没有合入。

相对 live worktree 的变更包括 HA-0085 退役事务、HA-0086 启动分类、HA-0087 详情全历史、HA-0090 中文切块与结构候选、HA-0092 清理错误隔离；HA-0088/89/91 属于评测或测试加固。中间版本的全文共现策略已被最终结构策略替换，不能按历史某个中间提交发布。

`backend/store.py`、`backend/service.py`、部署 plist/入口脚本和 Python/DSH/Pi 依赖锁文件均无差异。此检查说明没有这些文件的变更，不代替数据库备份或新版本启动验收。

## 发布前仍需完成

1. 单一操作者负责 live 分支与 8876 切换，其他会话保持只读；停服前重新确认 PID、监听者、工作区干净且无活动 Run。
2. 从实际 plist 确认数据库为 live worktree 下 `.local/dsh.db`，对实际数据库做一致性备份；当前只读预检没有创建备份。
3. 固定已复审候选、记录回滚点，再按既有会话级启动路径切换。`start_dsh_session.py` 要求 WorkingDirectory 与当前 ROOT 相等，而且会读取凭据引用做校验；本次没有执行它，隔离验证 worktree 不能直接冒充 live 部署目录。
4. 新进程必须核对 release、唯一监听者与 label；执行新的合成及小额真实公开合同冒烟，并核对多轮调用、预算、终态事件顺序、产物摘要和目录清理。
5. `verify_dsh_local.py` 读取的是 HA-0077 固定浏览器回执。它可以核对那些旧 Run 的持久结果，**不能作为本次候选新跑的浏览器或真实模型证据**。本次须另存新 Run ID、版本、用量及浏览器结果。

回滚运行代码参考旧服务 SHA `ad957fb`，live checkout 当时为 `5939e5d`；二者不能混称当前进程版本。回滚不得覆盖或回退已经发生的真实调用账本，也不自动恢复旧数据库覆盖新数据。

没有停服务、没有 Keychain 读取、没有 Provider 调用、没有写正式库；8765 和远端 132 未触碰。
