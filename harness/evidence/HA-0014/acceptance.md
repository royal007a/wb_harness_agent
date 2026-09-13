# HA-0014 验收结论

状态：passed（评测准备，不是模型准入）。

## 验收结果

- `intent-evaluation@2` fixture、`intent-shadow-candidate@1` 输出和 `intent-evaluation-policy@1` 均由机器 Schema 约束。
- Fixture 固定为 24 条手写 `synthetic_deidentified` 样例：不包含生产用户内容、个人数据或密钥。
- 影子候选必须绑定 fixture SHA-256、逐例覆盖、声明零工具调用及合成数据分类；额外的原文等字段会被拒绝。
- 评分器能机械拒绝缺失/重复 case、摘要不匹配和未达阈值的候选；策略只接受 `model_shadow` / `shadow`。
- 全量回归：135 passed，0 failures，0 errors；仅保留 1 条既有第三方弃用警告。

## 基线解释

`rules@1` 的扩展集诊断分数记录在 `rules-baseline.json`。它不是模型调用、不是影子候选，也不满足模型候选策略；8 个明确 gap case ID 用于防止将窄域 7 条规则回归误当成开放式语义路由质量。

## 不变边界

本验收未调用模型、未访问生产数据，未修改 `/api/local/intents:interpret`、Task 创建、引擎选择、权限或工作台交互。当前产品仍只运行 `rules@1` 本地 CSV 预检。
