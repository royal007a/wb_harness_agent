# ADR-0017：Plan / Evidence / Gap / Checkpoint 作为统一执行控制面

- 状态：Proposed
- 日期：2026-09-13
- 触发：用户要求将 Plan/Replan、TAO、Evidence State、Gap State 和 Checkpoint State 结合到当前 HarnessAgent 设计。

## 决策

采用 `PlanRevision`、`Evidence`、`Claim`、`Gap`、`CheckpointProjection` 与 `ReplanAttempt` 的版本化合同，作为现有 Product Task/Run/Step/Event/Artifact 的控制面扩展。G4C（Goal/Context/Choice/Checkpoint）是决策门禁；TAO 是一次执行循环；TCC（Try/Confirm/Cancel）是 ReplanAttempt 的状态协议。

计划、证据、缺口和检查点均为可追溯投影，不改变 Task 的不可变意图或 Run 终态。`supported` Claim 必须绑定 verified Evidence；可恢复 Checkpoint 必须固定资源/策略/预算等摘要；confirmed Replan 必须固定 Try/Confirm 摘要和新 Run 引用。Replan 不原地编辑 Run：确认后才创建绑定新 PlanRevision 的新 Run，并只允许使用经验证的剩余预算。输入资源、用户目标或权限扩大时必须新建关联 Task。

## 后果

- 现有固定 CSV 与研究演示继续只有取消/重跑；它们没有通过 restore 能力探针，不开放 Replan API。
- 先交付无模型、无副作用的 Schema、纯 reducer 与合成故障夹具；真实运行时需独立适配器探针、L3 测试和显式批准。
- Evidence 改善可追溯性但不能单独保证正确性；Claim 必须区分事实、推断和假设，并处理反证、时效和适用范围。
