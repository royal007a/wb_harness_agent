# HA-0014 模型化意图评测准备

状态：completed。用户于 2026-09-13 选择“启动模型化意图评测准备”。

## 已完成

1. 建立 `intent-evaluation@2` 合成去标识 fixture、影子候选输出和准入策略的 JSON Schema。
2. 添加 24 条手写样例，固定覆盖支持、澄清、范围外和安全边界四类表达；不含生产用户内容、个人数据或密钥。
3. 评分器校验 Schema、fixture SHA-256、case 一一覆盖、分类覆盖及影子策略阈值；它只处理本地 JSON，绝不调用模型。
4. 加入规则基线诊断、候选通过/阈值失败/原文与 case 覆盖拒绝测试；报告只输出 case ID 和结构化结果。
5. 补充安全、质量、ADR、技术债与回滚说明，并记录完整回归 Evidence。

## 结果与边界

- `rules@1` 在扩展集合的 24 条样例上是诊断基线，不是模型候选：决策/意图准确率为 0.667，拒识 recall 为 0.538；8 个 gap case ID 已记录。
- 此差距不改变现有受限预检，也不授权模型接入；它说明未来候选不能以原有 7 条固定样例替代更严格的安全/拒识评测。
- 没有模型端点、凭证、真实聊天、Task、资源、网盘数据或用户可见路由参与本任务。

## Evidence

- `harness/evidence/HA-0014/all-tests.xml`：135 passed；
- `harness/evidence/HA-0014/rules-baseline.json`：无原文诊断报告；
- `harness/evidence/HA-0014/manifest.json`：摘要、数据分类、gap 和 artifact hash；
- `harness/evidence/HA-0014/acceptance.md`：验收结论。

## 后续门禁

真实候选仍需用户提供获准端点、模型 ID、凭证引用位置、测试预算和允许发送的数据范围。候选必须先以 `model_shadow` 提交无原文结果，达到策略后也仅能申请下一阶段影子回放；用户可见模型路由另行审批。
