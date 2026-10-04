# HA-0071 FTS缺模块写入降级与故障不误吞

基线e8a3795。HA70已独立Approved；本项只修MEMORY-FTS-01，不擦除影子词项。

1. ADR-0071/spec登记后写缺模块生命周期和故障矩阵，先保存基线行为反例。
2. 限定创建语句的缺模块降级；可用时保留原子索引写入，不可用时M1写canonical。
3. 收紧查询故障传播；覆盖重启重建、错误类型/时机、持久快照和同key重试。
4. 相关Memory/Workbench、全量、verify、定向突变；固定提交交mymacclaude。
5. 真部署仍需兼容本机拓扑批准，先8765再132。禁止访问正式DB、Provider或凭据。

实现验证完成：新31/相关255；固定基线28行为失败、3通过；14有效突变被杀死。
全量1328 passed/16 skipped，verify退出0。初始化失败的连接/租约清理同步补齐。
7a03b99独立Approved，3 Low和孤立影子表信息记录于review.md；待兼容拓扑后的
双部署。不证明真实无FTS构建、实时索引身份/完整性监测或影子词项擦除。
证据harness/evidence/HA-0071/acceptance.md。
