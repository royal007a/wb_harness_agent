# HA-0039：Recovery Loop Guard 与 Team Gate 回接

状态：completed

风险：high（恢复/停止/交付语义；不涉及真实外部执行）

## 目标

在 ADR-0033 Team Task/Handoff/Gate 外新增一个独立、可审计、零执行的恢复控制面。每次失败显式保存四个位置；所有候选恢复必须受 Task、输入、Checkpoint、权限快照和预算约束，并且不能绕开 Handoff/Gate。

## 范围

1. 冻结 `recovery-loop-guard@1` Schema、错误目录与 ADR-0034；
2. 用 SQLite 记录 Case、Try candidate、Observation、Reminder 与 Cancel audit；
3. 提供本地 create/list/detail、observation、try、confirm、cancel、link-handoff、complete API；
4. 验证软/硬循环控制、版本/摘要漂移、零执行与 Team Gate 回接；
5. 通过后先发布本机，再同步 118.196.123.132，并保留无密 Evidence。

## 非目标

- 不执行模型、工具、真实 Checkpoint restore、外部补偿、真实取消、动态权限或自动审批；
- 不将根因假设写成事实，不把 Reminder 视为安全边界；
- 不修改 Product Task/Run 或把此旁路描述为通用 Agent Replan。

## 完成条件与结果

- Error Contract 由服务端稳定目录派生；失败点、根因假设、回滚 Checkpoint、Replan 起点分别可读：通过。
- Try/Confirm/Cancel 不产生副作用，Confirm 复核 Task/Checkpoint/权限/预算/输入绑定：通过。
- turn、时间、候选次数、单 operation 重复失败和取消被硬停止；连续失败/无进展只产生软 Reminder：通过。
- 只有同 Team Task 的 Handoff 加 Gate `pass` 才能把 Case 标为 `resolved`：通过。
- 6 项定向测试、231 项完整回归（12 skipped）、合成评测、本机和远端备份/发布/health/API/认证边界验证：通过。

Evidence：[`harness/evidence/HA-0039/`](../../harness/evidence/HA-0039/)。
