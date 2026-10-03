# HA-0058 OpenAPI 归属与 HTTP 实例验证

2026-10-04（北京时间）。状态：代码/离线验证完成，待固定提交独立 review；
真实双环境部署阻塞，不能称全部接口或系统已经验收。

## 发现与修复

- 基线 cd9b113 动态文档后写覆盖前写：Lab 的合法 ppr/mdl/agt ID 被 Runtime
  Schema 错拒，Lab 不支持的 credential_ref 被文档错放；研究 Skill 定义被 ZIP
  Skill 覆盖。492 条引用都存在，仍不能保证语义归属正确。
- `backend/openapi_contracts.py` 为21份源契约原子注册定义；Lab/Runtime/研究模拟
  显式命名空间；相同历史共享定义保留，异义重名报 OPENAPI_SCHEMA_COLLISION。
  只投影结构中的 `$ref`，不做整份 JSON 文本替换，不原地修改源契约。
- Lab/Runtime 两域现有 POST201、空/非空列表、状态、Session 详情、readiness
  使用源 JSON Schema，静态 OpenAPI 同步；测试覆盖请求、响应、逐帧 SSE、
  幂等重放、跨域 ID、未知字段、缺失对象及五种 readiness 状态。
- 不改请求 JSON、数据库 ID、业务授权或模型门禁。旧错误 component 名不保留
  别名，依赖动态文档生成的客户端需重新生成。

## 可复核验证

| 证据 | 结果 | 含义 |
|---|---|---|
| before.xml（cd9b113 未改实现） | 7 failed | 3 个正确 ID 错拒、credential 错放、研究 manifest 错配、2 个响应空占位；不是缺 helper/import 导致失败 |
| first.xml | 42 passed | 第一轮相关用例；不代替后续补充验证 |
| targeted.xml / http-observations.json | 101 passed | 新文件26项，加 Lab/Runtime/Research/Workbench；50入口观测、98未观测，仅定向样本 |
| full.xml / full-http-observations.json | 483 passed、16 skipped，52.48s | 完整 pytest + TestClient 观察器；131入口观测、17未观测 |
| verify.log | exit 0；483 passed、16 skipped，50.97s | 完整 verify.sh，包括清单、离线评测、脚本语法和 diff 检查 |

命令（均在本仓库 venv，临时 DB / 合成输入）：

```sh
.venv/bin/python -m pytest -q tests/test_openapi_contracts.py tests/test_agent_lab.py tests/test_agent_runtime.py tests/test_research_agents.py tests/test_workbench.py -p harness.pytest_interface_evidence --interface-evidence=harness/evidence/HA-0058/http-observations.json --junitxml=harness/evidence/HA-0058/targeted.xml --tb=short
env -u ARK_API_KEY .venv/bin/python -m pytest -q -p harness.pytest_interface_evidence --interface-evidence=harness/evidence/HA-0058/full-http-observations.json --junitxml=harness/evidence/HA-0058/full.xml --tb=short
bash harness/verify.sh
```

JUnit 的 targeted/full 参数化名称后处理为 `函数名[case_sha256=…]`（SHA-256
计算原名称首个 `[` 后的后缀，含闭括号），防止2MiB合成输入写入测试标题；
case数量、结论、耗时未改变。before只清除行尾空白。原始运行输出与退出码
已在执行时核对；没有修改断言、隐藏失败或把 skipped 当 passed。

两次全量分别带/不带观察器运行。观察器记录的 git_head 是修复前 cd9b113、
working_tree_dirty=true，source_sha256 绑定本次候选代码且前后不变；不是
宣称 cd9b113 自身已经修复。接口清单仍148个方法/路径、22类功能，无新增HTTP路由。

## 覆盖边界与未验收项

- passing test 的2xx只涉及130个入口；Channel详情只有403。131 observed不等于
  handler/分支/断言覆盖，更不等于131个功能完整验收。17个未观测入口见GAPS。
- 新测试显式禁止 credential.resolve 与 adapter.require；readiness只是本地元数据，
  ready_to_attempt不是成功接入。没有真实Provider/Keychain/第三方网络验证。
- Runtime默认关闭的SSE错误路径与Lab确定性演示已验证；不代替实际模型成功路径、
  客户端生成器或所有OpenAPI错误响应的兼容测试。
- 本轮未执行 launchctl、触碰8765服务、132、正式DB或部署拓扑；HA-0056拓扑决定
  仍待确认，必须本机验收后再132。此项不是部署成功回执。
- not_evidence：真实模型兼容、真实容器隔离、生产业务质量、所有接口功能验收、
  原生SubAgent/外部Skill→Product Run桥接均不由本轮证明。

下一步：固定提交给mymacclaude只读复审，重点挑战命名归属、拒绝空过、静态动态
实例一致性与注册原子性；保留未验证部署与剩余接口队列。
