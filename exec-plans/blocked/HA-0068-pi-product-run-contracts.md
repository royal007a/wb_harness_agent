# HA-0068 Pi Product Run

基线868f4b3。单一原子任务：Pi离线Product Run的五个HTTP入口与生命周期。

1. 先用临时DB和合成Adapter复现Gate重放、取消/提交竞态、500条分页和晚到Gate。
2. 按PI_PRODUCT_HTTP_CONTRACTS/ADR-0068修复并公布源/静态/动态合同。
3. 正反例、基线行为反例、定向突变、Workbench/全量/verify。
4. 固定提交交mymacclaude只读review；本机拓扑明确后先8765再132。

不启动真实Provider、Keychain或正式服务。真实sidecar测试与合成Adapter证据分开。

收口：38新增/185相关，旧30行为失败/8通过/errors0，9/9定向突变；全量1225
passed/16 skipped，verify退出0。143份源码哈希稳定。待固定提交独立review与
兼容本机拓扑明确后的先本机后132发布，证据HA-0068/acceptance.md。
