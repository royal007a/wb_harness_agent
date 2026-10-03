# HA-0057 验证（代码待复审，未部署）

基线 ce490c5。规格 PROVIDER_STREAM.md，决策 ADR-0057。
MockTransport 和临时 SQLite 验证 Provider 到 Exchange 的失败语义；不使用真实
模型、Keychain、用户库或远端服务。
实际部署仍受 HA-0056 本机拓扑约束，不能把离线协议测试称为已上线。

## 已验证

- `before.xml`：未修改基线 Adapter 上 4 个行为反例失败。delta 后 EOF、只有
  DONE 没有 stop、stop 后 EOF、length 后接 DONE 均被旧代码误判为下游 done。
  测试通过真实 Adapter + MockTransport + 临时 Store，非只测私有 helper。
- `targeted-first.xml`：首轮 38 passed / 2 failed，失败是 HTTP 重放测试漏带
  Accept:text/event-stream 而返回 406；补齐测试请求头，未放宽生产契约。
- `fixture-encoding-error.xml`：新增非法 surrogate 测试原先在构造 UTF-8 时
  collection error，改成 JSON 转义 surrogate 输入；失败保留，不称代码通过。
- `targeted.xml`：协议 56 项 + Runtime/Lifecycle/Workbench 合计 **132 passed**
  （5.71 秒）。正常 LF/CRLF/CR/BOM/逐字节中文、多行 data、usage、stop 带文本；
  所有非正常终止、畸形 JSON/类型/重复键、ID 漂移、帧/流上限、部分输出、HTTP
  SSE 与持久状态、幂等重放、等待取消/超时均断言结果与请求/关闭次数。
- 一批 1 MiB 空行仍会在首个文本 delta 前让事件循环 heartbeat 前进 10 次；
  解析按偏移扫描，避免逐行切掉整段缓冲导致二次方复制；每 4096 字节让出一次。
- `verify.log`：首次全量在清单门禁处停止，原因是新增功能映射后 INTERFACES.md
  未生成。运行官方生成器后重跑，没有跳过清单检查。
- `verify-final.log`：**exit 0，446 passed / 16 skipped**（47.04 秒）；清单
  148 个方法路径、22 功能一致；后续各定向/评测/JS/diff 检查通过。
  一个 Starlette/anyio BlockingPortal 的依赖弃用警告，不是失败。
- 凭据解析器为测试假对象，网络唯一传输为 MockTransport。默认 gate 关闭的
  回归明确断言解析凭据和 Provider 请求均 0；启用测试配置不改变部署开关。

## 边界与待办

独立 review 未收、真实模型/第三方兼容性未验证、双端未发布。协议 `supported`
不等于真实服务 available；usage 不构成费用硬上限；内存/CPU 限额不是 OS 沙箱。
没有增加工具执行、重试、fallback、Product Run 桥接或放宽准入。
HA-0056 ce490c5 代码已独立 Approved，但真实本机调用拓扑与双部署仍待完成。
