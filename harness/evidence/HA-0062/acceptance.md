# HA-0062 核心 Product HTTP 契约对齐

2026-10-04（北京时间），基线 d46f406。修正公开合同，不改变业务处理器返回值、
持久化逻辑或准入门禁。当前：代码回归及完整verify通过；固定提交独立review待完成；
双端尚未部署，不将本轮测试通过视作上线。

## 改动与旧版反例

动态OpenAPI的15个JSON成功响应不再是空Schema，另2个二进制响应声明实际媒体：
sample=text/csv、artifact download=实际media_type（通配声明）。17个入口的错误
声明统一使用当前middleware envelope；自动生成的422也不再误用FastAPI detail。
源定义在core bundle的local_http_*，静态/动态共享已有Task/Run/Event/Artifact。

静态漂移修复：创建响应没有links；Task详情是runs而非latest_run；cancel为200
且不用幂等键；Product events为JSON游标而非SSE。补资源详情和列表、任务列表、
产物列表/下载、CSV样本、PDF登记；rerun.reason可省略且允许自由文本≤2000字符。
历史目标approval标明未实现，API.md区分当前响应与未来示意。

`before.xml`在业务代码/静态动态Schema尚为d46f406时生成，19项全部失败：4项
静态漂移（实际HTTP被错误文档错拒/状态或media缺失），15项动态空Schema接受空对象。
均为行为断言失败，不是导入错误。后续52项包含这19项；不是52条旧版反例。
新增测试编写中曾出现缩进、错误码和rerun默认关系的预期错误，按现有代码修正；
这些不计为产品缺陷，也没有为迎合断言改变业务实现。

## 验证结果

| 证据 | 结果 | 范围 |
|---|---|---|
| before.xml | 19 failed | 修复前的4类漂移和15个空Schema反例 |
| test_product_http_contracts.py | 52 passed，10.31s | 新测试；静态/动态/源Schema均检查实际HTTP实例与负例 |
| targeted-http-observations.json | 190 passed，21.38s，exit0 | Product/OpenAPI/Workbench/Read四文件，68入口有passing-test 2xx |
| full-http-observations.json | 684 passed / 16 skipped，68.04s，exit0 | 148/148 observed且148有passing-test 2xx；不是业务验收率 |
| verify.log | exit0；684 passed / 16 skipped，67.76s | 完整verify，含离线评测、前端语法和diff检查 |

两份观察器记录d46f406+dirty，137个源码/契约/映射哈希运行前后一致；生成后
逐文件重算也一致。最终提交以这些哈希绑定候选代码，不谎称测试运行时已有新SHA。

```sh
env -u ARK_API_KEY .venv/bin/python -m pytest -q tests/test_product_http_contracts.py tests/test_openapi_contracts.py tests/test_workbench.py tests/test_read_surfaces.py -p harness.pytest_interface_evidence --interface-evidence=harness/evidence/HA-0062/targeted-http-observations.json --tb=short
env -u ARK_API_KEY .venv/bin/python -m pytest -q -p harness.pytest_interface_evidence --interface-evidence=harness/evidence/HA-0062/full-http-observations.json --tb=short
env -u ARK_API_KEY bash harness/verify.sh
```

## 断言及限制

- CSV任务创建/幂等重放→取消→基于原Run重跑→固定计算成功→终态取消不改，
  列表/详情/事件/产物都校验实际JSON；下载核对媒体、inline/attachment和字节哈希。
- GB18030、UTF8 CSV、Public PDF登记、两个研究引擎synthetic JSON及Child Run
  都在范围中；不把本地资源Schema限制到单一CSV成功样例。PDF样本只证明登记。
- 空对象、额外字段、嵌套状态/数值/哈希/日期损坏被拒；500条事件分页、游标空页、
  404/422/413/415/403实际错误体和可省略/边界/非法rerun请求均验证。
- 时间检查明确覆盖本服务输出的UTC子集，补偿当前环境FormatChecker缺少可选
  date-time依赖；不是通用RFC3339验证器，不宣称覆盖任意时区/闰秒。
- 所有HTTP均TestClient+临时SQLite；不触碰正式DB、8765、132或Keychain。
  native stream与Runtime凭据/Adapter设哨兵。没有Provider、真实容器或浏览器证据。
- 不是全OpenAPI完成：Memory、Research列表、Team及其他入口仍有占位；Schema
  校验不替代授权、对象引用一致性、时序或真实第三方兼容。16 skipped不算通过。
- 未改变全局$ref投影literal-data Low；未把health静态字段当release/Provider状态。
- HA-0061独立Approved及两条Low已记录：HEAD空正文仅传输层证据；sample与
  resource详情契约缺口由本轮修复。没有新增原始ASGI HEAD正文测试。
- 独立复审与实际双部署未完成。本机Background/gui域阻塞仍在，必须用户明确兼容
  拓扑后先本机、后132；不以文档变更为由静默切换launchd域。
