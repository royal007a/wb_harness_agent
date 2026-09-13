# HA-0021：本地 Replan Gap State 纵向切片

状态：completed（2026-09-13）。基于 ADR-0020，将用户已提供的执行图中的 Gap State 接入已批准的 ADR-0019 受限 TCC；验收证据位于 `harness/evidence/HA-0021/`。

## 目标

让固定统计的产物构建失败生成一个可追溯、可恢复、可验证的 Gap；Try 只允许引用这个 open Gap，只有成功的绑定恢复 Run 才解决它。

## 范围

1. SQLite 持久 `gap@1`、失败 Event 关联、open/resolved 状态和受控查询。
2. Source failure、Replan proposal/detail、恢复成功事件与 Gap 状态机的最小实现。
3. Schema/API/工作台提示、L3 反例、重启/取消/漂移/失败恢复和浏览器 Evidence。

## 非目标

- 新失败种类、模型根因分析、用户可编辑 Gap、权限/预算放宽、自由 Plan 或跨引擎恢复；
- 将 `resolved` 解释为业务结论正确，或修改源 Run/Checkpoint/Event。

## 验收

- 只有 `ARTIFACT_PUBLICATION_FAILED` 会创建一次核心 open Gap；无 Gap、已解决或字段不兼容时不能提案；
- Try/Cancel/Confirm 失败/恢复失败不解决 Gap；成功恢复才在新 Run 写 `gap.resolved` 并持久化状态；
- 全量/浏览器/Schema/安全/链接检查与 Evidence 通过，模型/网络/任意代码计数为 0。
