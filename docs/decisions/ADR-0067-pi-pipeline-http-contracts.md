# ADR-0067：Pi 离线管线的公开合同与流边界

状态：实现及离线验证完成，待固定提交独立复审与双部署；基线 5429c62，HA-0067。

现有 Pi 课程离线管线已有输出 Schema，但动态 OpenAPI 的五个成功响应为空，
review-stream 甚至声明成 JSON；静态流 data 只是任意对象，无法核验阶段数据。
决定复用原有源 Schema，以独立命名空间发布；增加 runtime 投影及区分三种
事件的流 Schema，静态/动态引用同源定义，错误采用当前 local_http_error。

不将原有 HTTP 请求投影和 SSE 前置计算改写成更强保证：额外字段忽略、
流 key 上限 120、Accept 子串判断、两次收据非原子等均明示并写行为测试。
这是契约补齐，不是 Pi 模型上线或法律评测。合法业务输出保持不变，客户端
需按明确响应重新生成。验收见 specs/testing/PI_PIPELINE_HTTP_CONTRACTS.md。
