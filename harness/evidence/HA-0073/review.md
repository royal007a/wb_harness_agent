# HA-0073 独立复审与返工

Reviewer：mymacclaude；固定版本d2e0538；结论Changes Requested。
飞书消息om_x100b632f14c5dca0c3de730cb49e925。

必须修：ZIP文件名声明UTF-8（bit11）但含非法字节，ZipFile构造器即抛
UnicodeDecodeError，原代码转500而非422。entry.py/manifest.json均可复现。
无落盘、无DB写入或执行，但与损坏输入契约不一致。

Low：非ASCII文件名规范化后误接受的突变未被旧50项捕获；生产代码依赖严格
固定文件名集合拒绝，没有发现绕过。此次补cp437及合法UTF-8非ASCII名反例。

Reviewer复跑50新/190相关（5跳过）、5241fe4上的50行为反例、12份突变XML；
另核实ZIP坏标志/压缩/CRC/路径/大小/JSON、多种程序异常仍传播、文件漂移、
旧审计兼容与边界。没有跑全量或真实Docker、entry.py、部署。

已披露而非新增保证：ZIP本地头尺寸与中央目录不同仍以中央目录解码；允许合法
data descriptor；manifest重复JSON键取最后值。其他Python版本的EOFError或
struct.error形态未验证，不笼统捕获所有异常为422。

返工：先规格与新反例，未修改生产代码时2个非法UTF-8文件名均500≠422，
其余9项通过。随后只在ZIP解析段增加UnicodeDecodeError捕获；其他构造器
ValueError/RuntimeError/MemoryError/EOFError/NotImplementedError仍为500。
证据见filename-before、filename-targeted、filename-verify；新候选待固定提交复审。

## 返工复审：Approved

2026-10-04 02:19 UTC收到mymacclaude对9cfc351的Approved。独立worktree只读，
新60项通过、测试SHA一致；恢复旧生产代码后2 failed/58 passed，放宽捕获为
ValueError/RuntimeError后3 failed。两个文件名反例和意外错误保护均有效。
未复跑1430全量或verify，未测其他Python版本、真实容器与双部署；不扩展批准范围。
