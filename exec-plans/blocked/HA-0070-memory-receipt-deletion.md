# HA-0070 Memory历史内容收据清理

基线1c9aaf5。只使用临时DB/合成数据，不碰8765、132、正式DB、模型或凭据。

1. 先登记ADR-0070和可执行spec，写HTTP生命周期/跨来源图依赖回归，固定旧版反例。
2. 同事务清理response并保留digest；启动旧库清理、同事务回放存在性检查。
3. 故障回滚、重启、并发和负例；定向突变确认删除/幂等/清理边界。
4. 定向、全量、verify并记录真实证据，固定提交交mymacclaude独立review。
5. 双部署仍按既有规则先本机后132；兼容本机拓扑未批准前不得跳过本机。

验证完成：新32、相关224、全量1297 passed/16 skipped、verify退出0；基线23行为
失败/5通过/4新Schema向量排除；12有效突变均被杀死。4c17c47独立Approved，
2 Low/1 Info已登记；待兼容拓扑后的双部署。证据harness/evidence/HA-0070/acceptance.md。
