# ADR-0058：OpenAPI 定义必须保留契约归属

状态：代码与离线验证完成，待独立 review；双端发布仍阻塞于 HA-0056 本机拓扑。
HA-0058，基线 cd9b113；证据见 `harness/evidence/HA-0058/acceptance.md`。

## 问题

app.py 逐次合并 `$defs`，后写覆盖前写。Lab/Runtime 的 provider/model/agent/
session/message 同名定义不同义；研究模拟与 ZIP Skill 的 skill_manifest 也不同义。
492 条引用都能解析，不代表指向正确契约。现有测试只验证引用字符串或源 Schema，
没有把已发布动态文档用于真实 HTTP 实例验证。列表等响应还缺结构约束。

## 决策

引入小型注册 helper，递归转换本地 `$ref` 并检查重名；三个冲突域显式命名空间。
其余历史定义仅在完全相同时复用，差异立即失败，不引入一个动态择优合并器。
Lab/Runtime 响应结构归入各自 JSON Schema，静态与动态文档共享它们，补实例测试。

不改变运行时认证、Provider 门禁、ID 格式或 JSON payload。当前工作不宣称完整
OpenAPI API 客户端生成验收，也不把元数据 Schema 变成业务授权；边界见
[测试规格](../../specs/testing/OPENAPI_CONTRACTS.md)。
