# HA-0081 部署记录（8876）

- 分支 `dsh/local-runtime-20261005` fast-forward 到 `27aee9f`（含 HA-0081 组装器与工具上限调整）。
- 停止前核对：launchd label `local.harnessagent.dsh-session` 的 PID 与 8876 监听 PID 一致（24884），只 `launchctl remove` 该 label；8765/132 未触碰。
- 启动 `deploy/start_dsh_session.py`；`/api/local/dsh/runtime` release `27aee9f`，`max_tool_calls` 32。
- 部署后真实验证（经 8876 HTTP）：long-01（18320 字）`run_ab68dec9a70a4b78a0056546d5bb6818` succeeded，7 次调用、74376 Token；pay-13（隐含例外）`run_4ea23a322f9f4b8e8eb12ac3ccf23dbb` succeeded，3 次调用、8039 Token；预留均归零。两条 Run 在页面历史中可查看。
- 中间版本 `873a5f7` 曾部署约 20 分钟，期间一次真实长合同 Run（`run_596538589c534ce9946dcf4dfb1d943a`）以 `DSH_PROVIDER_INVALID` 失败并冻结 1280000 预留（用量未知，按账本设计不释放），该 Run 已终止，不影响后续 Run 的独立账本。
- 回滚：`launchctl remove local.harnessagent.dsh-session`，在 `~/code/ai/harnessagent-dsh` 检出 `cbb3e9e`（HA-0080 版本）或 `c43df5b`（原始版本），再运行启动脚本。
