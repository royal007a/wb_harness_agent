# HA-0058 OpenAPI 合同归属与实例测试

目标：修复 OPENAPI-01 的同名覆盖；对两套本地聊天接口补真实实例契约验证。
范围：文档注册、JSON Schema、静态 OpenAPI、API 测试/证据，不改业务权限或部署。

1. 记录冲突证据，先补规格/ADR/任务。
2. 在 cd9b113 上运行能暴露错误归属/空响应的负例，保留失败。
3. 原子注册、隔离命名空间、两域响应合同，动态与静态同源。
4. 实例正反例、相关及全量验证，生成接口清单，固定提交交 mymacclaude review。
5. 实际发布依赖 HA-0056 本机拓扑决定，遵守本机后132，不伪报上线。

2026-10-04 检查点：1–4 的实现和测试已完成，2bd4af8已获mymacclaude独立Approved。
26 个新增用例，相关 101 passed；全量 483 passed/16 skipped，verify.sh exit 0。
148 个入口中观测到 131 个、17 个未观测；这不是业务断言覆盖率。
Evidence：`harness/evidence/HA-0058/acceptance.md`。

阻塞：真实发布仍取决于 HA-0056 兼容本机调用拓扑选择；不自动换 user/system 域，
不越过本机直接部署132，不开启真实模型。代码 review 与部署分别验收。
