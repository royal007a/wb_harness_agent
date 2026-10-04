# 外部Skill HTTP合同（HA-0073）

入口tests/test_external_skill_http_contracts.py；临时DB/包目录，镜像探针与执行器
显式合成，不启动容器或执行包中entry.py。

1. runtime的关闭/开启、镜像有无及两种backend状态；packages空/新建/去重/执行
   计数；成功和错误实例在源/静态/动态Schema一致，空对象/未知字段/错类型被拒。
2. 上传是application/zip，source_label沿用已有字符/长度约束，key1..128；执行
   严格JSON，公共错误含404/409/413/415/422/429/500/503，不能退回旧错误Schema。
3. ZIP文件名、数量、路径、符号链接、压缩方法/加密位、UTF-8、CRC、压缩损坏、
   深嵌套/超长整数manifest；失败不写DB、不启动Sandbox；128KiB+1拒绝。
4. 登记不执行；未启用先拒绝新执行，不读包。代理/非回环peer拒绝包访问，runtime
   仍可读；已执行的同key回放不读包/不启动容器，异body同key冲突。
5. 包摘要漂移拒绝执行；成功更新execution_count，失败不产生成功收据；执行器
   失败/提交故障之后释放锁，可再次请求；单执行器并发上限不能绕过。
6. 登记或执行DB中途故障回滚；文件目录可能残留但内容不可变，同key重试复核。
   重启保留包与历史回执；GET不写DB（不称不做镜像探测）。
7. 固定基线反例、定向突变、全量/verify和独立review；真实容器/部署另计。
8. 文件名编码单独验证：中央目录/本地头 bit 11 声明 UTF-8 但名称含非法字节，
   entry 与 manifest 两种名称都返回422；合法UTF-8非ASCII名、cp437非ASCII名
   也不得规整成允许的固定文件名。失败不写库、不创建包目录、不执行。
   只将文件名 UnicodeDecodeError 归为输入错误；ZIP构造器的其他ValueError、
   RuntimeError、MemoryError、EOFError、NotImplementedError保持500，不泄露异常。
