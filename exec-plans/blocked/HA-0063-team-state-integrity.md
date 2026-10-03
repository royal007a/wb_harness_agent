# HA-0063 Team持久记录完整性

1. 固定非法status、列/JSON scope分歧和Channel过滤反例，先写合同再改代码。
2. 临时DB HTTP旧反例失败；五类Foundation记录统一只读校验，合法inactive不变。
3. 正反例、目录/详情、写入和惰性过期回滚；相关和全量、verify、哈希证据。
4. 固定提交交独立review，实际双部署等待兼容本机拓扑，不绕过本机。

2026-10-04：1–3完成。最终测试放回7ac1498：旧18项行为反例失败；新增64项，
相关182通过，全量748 passed/16 skipped，verify exit0，138项源哈希稳定。
固定提交交独立review；实际发布仍等待本机兼容拓扑决定，因此任务blocked。
审计另发现TEAM-REPLAY-01（旧Session幂等键绕过当前访问资格），已单独登记，
不在本轮新key写入校验中冒报修复。证据harness/evidence/HA-0063/acceptance.md。
