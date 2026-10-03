# HA-0067 Pi 离线管线公开 HTTP / SSE 合同

2026-10-04，基线 5429c62。实现和离线验证完成，待固定提交独立复审及双部署。
规格 PI_PIPELINE_HTTP_CONTRACTS.md；ADR-0067；测试 test_pi_pipeline_http_contracts.py。

## 实现及兼容边界

- 五入口：Pi runtime GET、preview/review/security-check/review-stream 四 POST。
  源合同以 pi_admission_/pi_pipeline_/pi_guard_ 独立命名空间公开，不覆盖其他定义。
- 动态 SSE 从错误的 JSON 占位改成 text/event-stream，静态与动态均引用同源
  stream_event；三个阶段的 data 不再是任意对象。preview 状态与敏感命中、
  guard allow/deny 与 reasons、准入状态与开关/错误/摘要有明确关联。
- 保留原业务行为：HTTP 请求投影忽略额外字段，内部 request 仍严格；流 key
  上限 120、普通 key 128；Accept 子串检查；两份独立幂等收据。最终响应头
  Cache-Control 是中间件覆盖后的 no-store，不以处理器的 no-cache 冒充实际值。
- runtime 是档案投影，guard 是调用方 policy 的纯评估；都不是实际运行许可。
  流 done 不代表 Gate 通过或正式交付。本项不修改运行准入/业务执行。

## 新鲜验证

| 文件 | 结果 | 范围 |
|---|---|---|
| before-initial.xml/log | 5 failed，0.94s | 实现前五个公开响应为空或媒体类型错误 |
| initial.xml/log | 9 failed / 27 passed，5.81s | 草稿测试把源 $ref 与根 profile 约束叠加，且缓存头误按处理器判定；均纠正，非生产故障证据 |
| new.xml/log | 56 passed，9.60s | 最终新增测试 |
| before-final.xml/log | 54 failed / 2 passed，6.70s，errors=0 | 最终测试原样回基线，仅复制新文件，未复制新 helper 或生产修复 |
| targeted-initial.xml/log | 1 failed / 155 passed，17.28s | 原注册计数21需随三个新命名空间改为24；已更新精确断言 |
| targeted.xml/log、targeted-http-observations.json | 156 passed，17.60s | 8文件，含Workbench/OpenAPI；55入口观测，53有passing-test 2xx |
| full.log、full-http-observations.json | 1187 passed / 16 skipped，127.21s | 148入口有passing-test 2xx，不是完整功能/分支验收率 |
| verify.log | exit0 | 全量1187 passed/16 skipped，122.85s；检索2/Agentic2/adaptive6及离线评测、准入检查、JS语法、diff通过 |
| mutations.md、mutation-*.xml/log | 8/8定向突变被杀死，errors=0 | 单处突变，逐次还原并cmp确认 |

最终新增测试 SHA-256：60367cf1950c87bc6356a617aa9ca7f463ee62184ed65d594bc212bb60570d62。
基线文件哈希一致；54个失败多为同一空声明/缺公开合同，不是54个独立生产bug。
两项旧版通过是 Accept 含 text/event-stream 的正常流行为，本次没有改变它们。
新增用例补入时曾有一次测试尾部落错函数导致 NameError（55 passed/1 failed），
已纠正再冻结；不以脚手架错误充当旧版反例，最终基线及突变均为行为失败。

观察器记录 5429c62+dirty；142份源码/契约/测试/映射哈希在测试前后及收口时一致，
不把候选工作树测试伪写成最终 commit 上执行。targeted两份XML的212个参数化
用例名改为摘要，生成日志/XML清理行尾空白，结果未改写。

## 不证明什么

- 测试是 TestClient、临时 SQLite、生成 PDF，未触碰8765/132/正式DB/Keychain/
  真实Provider。禁用执行和 sidecar/凭据/Adapter 哨兵；不是 OS 级隔离或真实
  socket 背压/断线/逐 Token 体验证据。
- 敏感匹配只验证固定模式命中与流 heading 中和，不证明检测召回率或法律正确性。
  普通 preview 的 heading 仍可含非敏感标题文字，不能称所有接口零原文片段。
- 源 Schema 和公开声明不是新增运行时响应拦截器，不自动修复损坏存储。
  runtime blocker_count 与数组长度的一般等式由行为测试检查，不是JSON Schema算术。
- 16 skipped 不计通过；Pi Product Run 五入口及其 Gate/事件分页本项未补契约。
- remaining-empty-responses.json：仍有30个API成功JSON Schema恰为空，加1个页面；
  不包括缺content或非空但过宽声明，不能当作全部剩余问题计数。
- 独立复审与先本机后132双部署另行验收；HA-0056本机拓扑批准仍未取得。本轮
  未执行launchctl或远端操作，离线通过不解除部署前提。
