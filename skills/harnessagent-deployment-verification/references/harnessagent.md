# HarnessAgent 项目映射

这些是发现线索，执行前重新核实。用户指定范围优先；同机存在两个独立分支，不能把8765当成DSH。

| 目标 | 本机 | 132现有服务/数据 | 用户入口 |
|---|---|---|---|
| 客服 | support checkout，8765，local.harnessagent.support-session | harnessagent.service，/opt/harnessagent，/var/lib/harnessagent/harness.db | https://118.196.123.132/harness/support |
| DSH | dsh checkout，8876，local.harnessagent.dsh-session | harnessagent-dsh.service，/opt/harnessagent-dsh链接，/var/lib/harnessagent-dsh/harness.db | https://dsh.118.196.123.132.nip.io/dsh |

本机/远端源目录与进程版本分别取证。不要把文档收尾SHA当运行SHA，或把旧进程持有的release当磁盘当前HEAD。实际HARNESS_DB以运行进程/服务和打开文件交叉核对。端口、PID、DB、版本与代理路由成组绑定。

项目AGENTS要求实现变更先本机健康再132发布；仅skill/spec维护不触发部署。DSH远端不能自动复制本机Keychain、SQLite或把真实Provider门禁打开。客服原有自动探针可能自然更新health与计数，不能声称全服务器零模型调用。

132的上述两个公布入口均必须使用HTTPS，plan不得改为HTTP/tls=not_applicable；HTTP重定向只能另列检查。公布地址有授权变更时先更新验收spec与登记的plan。

公共入口验收要保留HA-0117暴露的差别：TLS原域名失败、服务器本地可读、SSH转发可读、IP+Host成功是不同事实。允许诊断绕行，不允许据此写“公网验收通过”。已有自签证书的例外必须单列，不代表CA信任通过。

引用项目中的specs/testing/DEPLOYMENT_VERIFICATION.md及LOCAL_DEPLOYMENT_RECOVERY.md。后者约束特定旧launchd助手，不应把其“模型必须关闭”跨用到已有独立准入的服务。对新环境按当前授权门禁核对。

回退前确认共享依赖：DSH新worktree可能复用旧目录的node_modules及Git元数据；未解除依赖前不能清掉旧发布。客服rsync promotion需显式保留运行时目录；staging的排除规则不等于live端的保留规则。
