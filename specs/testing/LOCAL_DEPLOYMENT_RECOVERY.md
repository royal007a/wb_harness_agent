# 本机发布恢复验收（HA-0056）

对应 DEPLOY-01。只修改既有 launchd 发布助手；不改变应用、凭据、沙箱准入、
数据库内容或公网访问边界。回退 plist 不等于回滚应用代码或数据库。

1. 发布前仍要求干净提交、批准的 plist、可用固定沙箱镜像、SQLite 一致备份。
2. 在任何 bootout 前预检调用方 managername、目标 gui 域、当前/恢复 plist 的
   Label、工作目录、启动命令与会话类型。Background 调用方不得尝试 gui 激活；
   预检失败不停止服务、不执行 bootstrap。user 域方案须另行批准，本版本不自动切换。
   exit 5 可能表示配置/会话错误或已加载，不再默认重试；bootstrap 单次最多 5 秒，
   失败记录动作、exit_code、attempts 或命令超时，不用最后一次超时掩盖既有错误。
3. 服务启动不能用 sleep 成功代替健康验证。最多 60 秒读取 health、模型门禁
   和外部 Skill 状态；模型必须关闭，Skill 必须沿用批准的 Colima profile。
   bootstrap 前必须等待 label 消失且 8765 不再监听（最多 15 秒），未知端口占用
   不强杀。启动后 launchd PID 必须等于唯一监听 PID，记录进程启动时间；每轮健康
   检查前后重新核对身份与干净提交，不能接受旧进程、PID 改变或代码漂移的应答。
4. 正向启动失败，只卸载本应用 label，并尝试恢复备份 plist；恢复也使用
   同样的预检、受控停机和健康验证。bootout 失败/超时也不得忽略。
   原发布仍返回失败，不写成功 deployment.json。未停止任何服务的预检失败不恢复。
5. 恢复成功或失败均写 activation-failure.json（错误类型、步骤、健康结果），
   不保存命令 stdout/stderr、环境变量或凭据。不能将“发过 bootstrap”记为恢复。
   KeyboardInterrupt 同样写失败回执，不自动继续发布；恢复明确记录仍运行当前提交，
   code_rollback=false、database_rollback=false，原提交仅表示恢复 plist 的来源。
6. 不强杀其他进程、不自动回滚 DB、不移植本机数据或凭据到 132。

故障注入：Background/gui 不兼容、域不可访问、已加载、永久 5、非 5、命令超时、
端口延迟释放/被未知进程占用、旧 PID 应答/身份变化、启动后健康失败、
回退成功／失败、KeyboardInterrupt。测试用临时 SQLite 和 fake launchctl/HTTP，不操作
真实 launchd。另做固定提交的本机发布、132 同步和健康核对；模拟失败不等于
已覆盖操作系统全部故障模式。
