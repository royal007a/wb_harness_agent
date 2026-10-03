# 全系统功能与接口测试规格

本目录是用户要求的全系统验收入口，不以 pytest 通过数代替功能完成度。
基线从 HA-0053 开始；有效约束来自 CORE_CONTRACTS、QUALITY、各功能规格和
对应 ADR。参考课程用于挑战设计，不能替代运行证据。

## 清单与执行

- `features.json`：人工维护的功能、实现边界、规格和测试入口，包含非 HTTP 功能。
- `interfaces.json` / `INTERFACES.md`：从**实际注册路由**生成的 HTTP/页面/静态入口，
  包括 OpenAPI 隐藏的 callback；变更后用以下命令重建并提交。
- `harness/evidence/HA-0053/http-observations.json`：测试请求观测，不是验收结论。

```sh
.venv/bin/python -m harness.interface_inventory --write
.venv/bin/python -m harness.interface_inventory --check
.venv/bin/python -m pytest -q -p harness.pytest_interface_evidence \
  --interface-evidence=harness/evidence/HA-0053/http-observations.json
bash harness/verify.sh
```

观察器只记录路由模板、方法、HTTP 状态码、测试 ID/结果和代码摘要；不记录
具体资源 ID、Query、请求/响应正文或凭证。2xx 请求也可能来自 Mock 或只验证了
状态码，**observed 不表示 validated**；403 可能在中间件返回，不能当作业务
处理器覆盖；SSE 的 HTTP 200 也不能说明流中的 done/error 已验收。
pytest 自动参数 ID 可能包含整段 fixture，因此观察器仅保留测试函数名，
参数段改存 SHA-256；不把测试参数正文当作无敏元数据。

## 每个接口的验收要求

1. 正常请求：请求/响应符合所属规格，业务字段和持久状态符合预期。
2. 无效输入：未知字段、缺字段、类型/范围、媒体类型、正文大小、路径/Query；
   断言具体错误码和无副作用，不能只断言任意 4xx。
3. 权限和门禁：同源/代理/身份 scope、模型/网络关闭、来源/摘要漂移。
4. 写入：幂等重放/冲突、并发、重启持久性、失败时事务不留半成品。
5. 生命周期：适用时检查取消、超时、预算、终态不可覆盖、恢复兼容性和清理。
6. 部署：本机根路径与 132 `/harness/` 前缀一致，认证保留；隔离失败不得降级。

每项要有测试 node ID、断言说明及新鲜运行结果。未适用须说明理由；缺少证据
保持 missing。非 HTTP 功能同样须验证公开 CLI/入口，而不只调用内部 helper。

## 证据层级

| 标记 | 可以证明 | 不能证明 |
|---|---|---|
| static_contract | 规格/Schema/清单一致 | 实际运行行为 |
| deterministic | 本地固定算法、临时 DB、反例 | 模型质量、外部服务连通 |
| mocked_transport | 协议、错误/取消注入 | 真实 SDK/Provider/凭据 |
| real_container | 当次主机/镜像隔离与执行 | 另一主机、多租户、模型判断 |
| browser | 当次 UI/前缀/交互 | 未执行的后台分支 |
| live_external | 经准入的真实外部链路 | 其他配置或数据范围 |

关闭的能力必须验证拒绝路径，但其真实运行仍记 blocked/not_verified，不记通过。
所有修复须有旧代码能失败的新回归测试，并在适用环境重跑。

## 整体完成条件

清单无遗漏；逐功能和接口的必需用例完成；发现的问题已修复并交独立 review；
本机及 132 发布/健康/功能证据对应同一应用版本；未获授权的外部门禁仍关闭。
若真实能力验收缺授权/凭据，应单列缺口，不得把它从用户完整目标中悄悄删除。
