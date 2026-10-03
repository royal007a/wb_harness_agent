# HA-0062 Product HTTP契约对齐

1. 固定旧版及四类文档漂移，登记规范与任务。
2. 以真实临时DB HTTP响应作正例，旧Schema错拒/空Schema错放的测试先失败。
3. 共享HTTP封装定义，修正动态绑定、静态字段/状态/媒体类型，保持业务响应不变。
4. 核心完整生命周期、混合资源/研究Run、错误与下载回归；全量/verify/观察器。
5. 固定提交交mymacclaude独立复审；真实发布仍等待兼容本机拓扑，不跳过本机。

2026-10-04：1–4完成。旧19反例全部按行为失败；新52、相关190通过；全量
684 passed/16 skipped，verify exit0，137项源码哈希运行前后一致。实际注册入口
仍148项，17项Product成功/错误/下载声明对齐；未冒充全OpenAPI完成。
7ac1498已获mymacclaude独立Approved；4组Low已记录，before.xml的早期测试
版本限制已纠正，未称当前测试可原样复现全部19项。任务因实际双部署仍需本机
兼容拓扑决定而blocked。
不更换launchd域，不跳过本机先发132。证据：harness/evidence/HA-0062/acceptance.md。
