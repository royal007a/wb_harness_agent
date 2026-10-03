# HA-0057 验证（986ed1d 含追加修复已独立 Approved，未部署）

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

85fc7d3 与 986ed1d 独立 review 均 Approved；真实模型/第三方兼容性未验证、双端未发布。协议 `supported`
不等于真实服务 available；usage 不构成费用硬上限；内存/CPU 限额不是 OS 沙箱。
没有增加工具执行、重试、fallback、Product Run 桥接或放宽准入。
HA-0056 ce490c5 代码已独立 Approved，但真实本机调用拓扑与双部署仍待完成。

## 独立复审（85fc7d3）与压缩响应 Low

2026-10-04 mymacclaude 只读复审给出 Approved：独立重跑 56 项通过，四条旧版
误发 done 反例均行为失败，另做 39 个协议边界/限额/资源/持久化探针。其输入、
编码边界和每路径一次关闭/一次请求是 reviewer 报告，不伪称本代理运行了该套探针。
剩余 Low 为 `aiter_bytes()` 解压先于大小检查；reviewer 报告约 61 KB gzip
展开约 60 MB，tracemalloc 峰值 144 MB。该峰值亦非本代理本轮测量。

补丁先更新规格，再在尚未修改的 85fc7d3 Adapter 上运行新增测试：
- `encoding-before.xml`：11 failed / 56 deselected（0.95 秒），全部为行为失败，
  非缺符号/导入失败。gzip 报错太晚，deflate/identity/空值/未知值会接受或读取；
  decoder 哨兵证明旧路径确实进入 HTTPX 内容解码器，HTTP 也报错太晚。
- 新路径固定请求 identity；存在任意 Content-Encoding 立即拒绝；无编码使用
  `aiter_raw()`。9 种编码输入 body_reads=0、close=1、request=1；另用 decoder
  哨兵验证正常路径不调用解码器，用 HTTP/临时 SQLite 验证无预览、无交付及重放。
- gzip 夹具通过流式压缩 960 个 64 KiB 空行块生成（总解压体积 60 MiB），
  测试构造无需保留整份明文。断言“未迭代正文”而非不稳定的进程峰值阈值。
- `encoding-targeted.xml`：新增 11 项 + 原协议 56 项，**67 passed**（1.44 秒）；
  `encoding-related.log`：再含 Runtime/Lifecycle/Workbench 76 项，**143 passed**
  （5.86 秒）。大正文参数采用短测试 ID，避免 XML 将合成 body 写入用例名称；
  仅调整测试标签，无输入或断言变化。
- `encoding-verify.log`：完整 verify **exit 0，457 passed / 16 skipped**
  （47.46 秒），清单、后续确定性评测、JS 与 diff 检查均通过。

不声称整个 HTTP 栈/OS 缓冲具备 2 MiB 内存硬限额。没有实际模型/真实端点、
Keychain、8765 或132操作，部署阻塞不变。

## 编码修复独立复审（986ed1d）

2026-10-04 mymacclaude Approved，重跑 67 项全部通过。另以本机合成 HTTP
server + 真实 h11 socket 验证：约 61 KB gzip（展开 60 MiB）读取前拒绝，
报告 tracemalloc 峰值 4.2 MB；未压缩约 5 MB 输入报 RESPONSE_LIMIT、峰值
5.9 MB；两次各一个请求。以上内存数字来自独立 reviewer，不是本代理重测。
没有真实第三方 Provider、8765、132 或双端发布证据；强制压缩网关仍 fail-closed。
