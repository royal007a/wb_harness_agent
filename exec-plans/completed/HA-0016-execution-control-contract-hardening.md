# HA-0016 执行控制合同完整性硬化

状态：completed（2026-09-13）。只修正 HA-0015 审查发现的离线合同缺口，不接入运行时。

## 目标与非目标

目标：让“有证据的 Claim”“可恢复 Checkpoint”“已确认的 Replan”在机器 Schema 上具备不可绕过的最小绑定，防止文档规则只停留在口头约定。

非目标：新增 API、数据库迁移、Run 恢复、模型/工具调用、改变 CSV/研究引擎语义，或把 Proposed ADR 描述为已接受。

## 现状证据

HA-0015 的首次合同允许 `supported` Claim 没有 supporting Evidence，也未把 Checkpoint 的资源/权限/剩余预算摘要与 Confirm 结果固化到 Schema。纯 reducer 不受影响，但未来运行时可能错误地把不完整记录当成可恢复状态。

## 变更步骤

1. 对 supported/contradicted/retracted Claim 加入 Evidence 与可信状态条件。
2. 为 CheckpointProjection 加入 checkpoint、adapter、resource、权限和剩余预算摘要，并把 `restorable` 与 verified/adapter restore 能力绑定。
3. 为 ReplanAttempt 加入 Try 摘要、Confirm 绑定摘要和 confirmed Run 引用；未完成绑定不得进入 confirmed。
4. 增加反例契约测试，更新控制合同/ADR，执行全量回归和独立 Evidence。

## 验证与回滚

验证：Schema 反例、HA-0015 合成评测、全量 pytest、链接/任务 Schema/diff 检查。回滚：该任务只收紧新增 Proposed 合同，无数据库或 API 迁移；回退相应 Schema、测试和文档即可。
