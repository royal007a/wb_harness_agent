# ADR-0069：Memory写入回执及失败边界

状态：实现中；基线697ef73，HA-0069。

复用M1来源优先模型，公布Retain、retract、delete的实际回执，不新增执行权限。
Retain内容去重与首次写入、重复撤回与首次撤回具有不同形状，使用明确分支，
不把历史收据误写成当前Source/Fact状态。删除后同key回放返回历史删除收据。

损坏本机semantic准入文件（含非UTF-8、过深JSON、超长整数）应返回
invalid_not_admitted，而非使Memory状态接口500。只输出异常类型，不输出路径
或正文；runtime_enabled恒false。真正DB或程序故障不吞成无历史。

DELETE不接受任何非空请求体：不能只信Content-Length；收到第一个非空流片段
即拒绝，不缓冲整个body，不执行业务。请求体和幂等键验证顺序不授予删除权。

兼容性：合法返回不变；原先被忽略的分块body现在422。Schema收紧公开声明，
没有新增认证。全库抹除（包括历史幂等收据）、FTS不可用时的写入恢复、
物理磁盘/WAL擦除不在本轮；必须登记而非宣称已完成。

验收见specs/testing/MEMORY_WRITE_CONTRACTS.md。
