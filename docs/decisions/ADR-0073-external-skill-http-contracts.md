# ADR-0073：外部Skill HTTP合同和损坏包输入边界

2026-10-04；Accepted for implementation。基线5241fe4。

runtime、packages GET/POST尚无成功响应Schema；execute已有但audit过宽，四入口
错误信封也未绑定当前HTTP规则。本轮补明确的状态/包/列表/审计形状和三套实例
验证；不增加任何执行入口、权限、挂载、模型或部署开关。

ZIP入口限定无加密的stored/deflated两个方法，继续只允许manifest.json和entry.py。
加密位1、强加密位64与不支持的patched-data位32都在读取条目前拒绝。
损坏压缩数据、深嵌套/过大整数manifest应作为422输入错误，不能泄漏原始异常；
不把DB/文件系统/其他程序错误宽泛吞成输入错误。128KiB压缩包、每项64KiB和
manifest Schema限制保留；不实现宿主加载第三方代码。

runtime查询实际会探测镜像（可调用Docker CLI），不是零I/O或容器ready证明。
列表带实时runtime与execution_count；上传和执行幂等收据是历史快照。关门后同key
可回放既有执行收据但不会新执行。合成Sandbox只证明控制面，不替代真实隔离探针。

DB与受控文件目录不构成跨资源事务：DB回滚时可能留下已按摘要固化的包目录，
重试复核摘要再复用，不覆盖漂移文件。执行完成但DB提交失败后，同key重试可能
再次执行；现有受限JSON transform不承诺跨容器/DB的exactly-once。

现存审计记录可能来自HA52之前，没有backend；保持该字段可选，其他已写字段
收紧类型/摘要/时间/清理标记。这不是完整供应链认证、取消协议或多租户沙箱。
