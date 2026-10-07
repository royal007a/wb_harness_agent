# 部署验证合同（HA-0118）

适用于本项目的新发布、重部署与发布复核；skill/spec维护本身不发布业务服务。现有授权继续有效，不以本文制造重复确认。具体旧launchd助手仍遵守LOCAL_DEPLOYMENT_RECOVERY.md，本合同不改变已批准的运行门禁。

1. 计划绑定用户要求、固定版本、逻辑服务、实际监听、数据库和公开入口。客服与DSH独立列项；两条分支不能互相替换。spec写明每个必过项的触发、可观察结果和证据，不在失败后自动降级必过条件。
2. 发布事实与验收结论分离：reported_deployment_status只记录动作结果；verification为verified、verified_with_exceptions、failed、incomplete或invalid。一个目标失败不能被另一个目标成功平均掉。用户入口未过时，报告“已部署；公网验收失败/未完成”；若任务要求公网可用，不得自行标记整个任务完成。
3. 版本/实例：确认运行进程/容器和唯一监听属于目标服务，记录启动时间；检查前后身份稳定、实际运行版本与目标一致。磁盘HEAD不能代替旧进程持有版本，read-only复核旧Run不能代替新版本执行证据。
4. 备份/保留：从当前服务解析并交叉核对真实数据文件，备份后验证摘要、权限和读取/完整性。恢复演练另计。数据保留验证须超越行数，允许变化字段具名说明。rsync明确保留运行时目录；worktree、Git元数据、node_modules及回滚引用必须纳入依赖清理判断。
5. 测试按变更选择。UI小改动使用已有路径/DOM与实际浏览器，不为低影响可逆变更追加同构测试。运行时/依赖变更增加适用探针；合成、真实Provider和旧Run读取分开标注。不得扩大模型费用或凭证授权。
6. 公网以公布URL从目标用户访问路径核验，分别记录DNS、TLS、认证、静态资源、业务DOM和脚本错误。401只证明认证拒绝；loopback/SSH/IP+Host/DNS覆盖及关闭TLS校验只作明示的诊断/例外，不能顶替原入口必过项。项目既有自签TLS例外只能给带例外的限定结论。
7. 失败尝试、跳过项、并发干扰和退出码来源不可丢失。CLI真实exit应单独记录，不能从日志最后一行补造exit0。临时身份在所有退出路径清理，结束后再核对；测试中途存在不等于结束残留。截图须等待最终状态且人工检查。诊断结论限定当前网络，不凭一个客户端推断所有用户均不可达。
8. 验证脚本默认不产生业务写入。保持已有授权内的有界诊断与回退；未知结果不重放外部副作用，不能为了通过而改无关网络拓扑。发布、应用回退、配置恢复和DB恢复分别取证。

## 可移植skill与机器合同

入口：`skills/harnessagent-deployment-verification/SKILL.md`；通用合同：`references/evidence-contract.md`；本项目条件：`references/harnessagent.md`。安装到Codex和Claude的相同目录内容需逐文件摘要核对。

`scripts/verify_receipt.py`使用Python标准库，只读plan、receipt与证据文件。plan摘要锁定已声明要求；核心release/identity/health、条件适用的public_entry、实际DB对应backup/preservation不可缺。它比较expected/observed、逐字节核对证据SHA、限制文件读取根目录并保存历史失败计数。它不联网、不执行日志命令，也不证明观测真实、验收计划完备或系统安全。

exit0仅表示该声明范围verified或verified_with_exceptions；exit1表示failed/incomplete；exit2表示输入或证据无效。项目验收人仍必须对照真实命令和外部观测，不能把离线校验器通过冒充在线验收。

## 离线反例

至少覆盖：旧版本、健康可用但公网缺失、SSH/IP替代、URL变化、TLS校验降级与显式例外、UI仍有入口而200、多个服务一败一成、必过项跳过、计划事后改变、未知检查、失败后重试留痕、退出码缺失/False、错误DB路径、证据缺失/篡改、越界/符号链接、重复JSON键，以及证据中命令不被执行。测试使用临时文件和合成声明，不触碰8765/8876/132、凭证或Provider。
