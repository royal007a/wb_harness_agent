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
   bootstrap 前必须等待 label 消失且 8765 不再监听（最多 45 秒，包含命令等待）；
   bootout 单次最多 30 秒，覆盖批准 plist 的 ExitTimeOut=20 秒退出窗口。
   plist 不得通过 Program 覆盖启动命令；ExitTimeOut 仅接受缺省或整数 20。
   观察命令因剩余窗口耗尽而超时，报 teardown_deadline，不丢失最后观察到的
   label/listener 状态；窗口尚未耗尽的命令超时另行记录。未知端口占用
   不强杀。启动后 launchd PID 必须等于唯一监听 PID，记录进程启动时间；每轮健康
   检查前后重新核对身份与干净提交，不能接受旧进程、PID 改变或代码漂移的应答。
4. 正向启动失败，只卸载本应用 label，并尝试恢复备份 plist；恢复也使用
   同样的预检、受控停机和健康验证。bootout 失败/超时也不得忽略。
   唯一例外是本次助手已经识别且正在退出的进程：label 消失但该进程仍占端口时，
   恢复预检只允许 PID 与停机前启动时间均相同、且没有其他监听者的进程继续有界退出。
   不将它当作健康新发布、不再次发送 bootout、不按裸 PID 放行复用进程；端口未释放
   绝不能 bootstrap。第二个等待窗口也最多 45 秒，耗尽仍失败，不无限等待或强杀。
   原发布仍返回失败，不写成功 deployment.json。未停止任何服务的预检失败不恢复。
5. 恢复成功或失败均写 activation-failure.json（错误类型、步骤、健康结果），
   不保存命令 stdout/stderr、环境变量或凭据。不能将“发过 bootstrap”记为恢复。
   激活开始后的 KeyboardInterrupt 同样写失败回执，不自动继续发布；恢复明确记录仍运行当前提交，
   code_rollback=false、database_rollback=false，原提交仅表示恢复 plist 的来源。
   回执分别记录 bootout_attempted、bootout_returned、service_stopped（只有观察到
   label 消失且端口释放才为 true），不能以 phase 推断已停机。恢复中 Ctrl-C 也在
   写回执后重新抛 KeyboardInterrupt。因两个 plist 必须符合同一批准命令/目录/门禁，
   此恢复仅涵盖日志、KeepAlive 等非执行配置，不恢复旧代码、旧环境或其他命令。
   备份准备阶段尚未停服务，中断不写激活失败回执，可能留有未完成备份目录，不能
   将其作为可恢复备份使用。KeepAlive 重启导致身份变化仍保守拒绝；ps 恰好观察到
   已退出进程可重查，但不接受新身份冒充原身份。
6. 不强杀其他进程、不自动回滚 DB、不移植本机数据或凭据到 132。

故障注入：Background/gui 不兼容、域不可访问、已加载、永久 5、非 5、命令超时、
端口延迟释放/被未知进程占用、旧 PID 应答/身份变化、启动后健康失败、
回退成功／失败、KeyboardInterrupt。测试用临时 SQLite 和 fake launchctl/HTTP，不操作
真实 launchd。另做固定提交的本机发布、132 同步和健康核对；模拟失败不等于
已覆盖操作系统全部故障模式。
