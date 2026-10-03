# HA-0052 外部 Skill 双环境受限启用

2026-10-03。应用发布：`87934de73ab314963509dfe3feff5a2fef8fde85`。
实现提交：`2303561`；离线镜像发布补充：`87934de`。

## 已交付

- 显式 `colima` / `linux-docker` backend，不再把 Linux 强制连到 colima。
- 两个批准部署显式启用 Skill；代码默认仍关闭；模型/语义检索/Claude Gate
  不变。公网可读无密 runtime 元数据，包读写/执行仅直接 loopback 或 SSH。
- 宿主流式读取输出并在 32 KiB 硬停、禁用容器日志，异常/超时清理；单服务
  同时一个执行、忙时 429，阻塞 Docker I/O 不占用 asyncio 事件循环。
- 固定版本发布、SQLite 真实路径备份、nginx/systemd/launchd 配置备份/回退
  及可重复的 `harness/external_skill_smoke.py` 合成 API 验证。

## 验证证据

| 检查 | 结果 |
|---|---|
| 本机 `bash harness/verify.sh` | 303 passed / 16 skipped，后续评测和 JS 检查均 exit 0 |
| 本机 Skill + workbench 实容器定向 | 73 passed |
| 本机独立外部 Skill 全测试 | 17 passed（包括 5 个真实容器用例），见 local-external-skills.xml |
| 132 独立 staging 全量测试 | 297 passed / 22 skipped |
| 132 线上依赖 workbench/frontend 预检 | 60 passed |
| 132 外部 Skill 全测试 | 17 passed（无 skip），见 remote-external-skills.xml |
| 两端线上实际 API | 合成 [2,3,5] → sum=10、uid=65532、断网、宿主/socket 不可见、清理成功 |
| 本机/132 health | ok，model_calls_enabled=false |
| 公网未认证页面 / runtime | 401 / 401，保留既有 Basic 边界 |
| 公网包列表 / 执行 POST | 403 / 403，拒绝发生在执行之前 |
| 所有外部 Skill 标签的容器 | 验证后两端均无遗留 |

默认全量 skip 是显式容器探针和环境特定能力，不声称全部引擎已验证。
真实容器测试覆盖禁网、非 root、无宿主环境凭据继承、宿主路径/socket 隔离、
只读根/输入、死循环超时、原始 fd 输出洪泛与清理。单元测试覆盖默认拒绝、
代理/非回环入口、并发上限、幂等重放、篡改和非法 backend。

## 构建过程中发现并处理的问题

1. 132 Docker Hub 连接超时，第一轮发布在 staging 停止，未切换线上服务。
2. Mac legacy builder 使用多架构索引跨编译时，导出包的 amd64 config
   对应了 arm64 基础层。132 `docker load` 输出 wrong diff id，17 项测试中
   5 个真实容器用例无法启动；绝不把 tag 可 inspect 当作镜像可运行。
3. 直接从官方 registry 读取已固定索引并核对原始字节 SHA-256，确认其
   linux/amd64 子摘要为 `2fe5997d…18ce79`。用该子摘要替换 FROM（其他指令
   和 runner 不变）重建；导出包 7 个层的实际未压缩 SHA 均与 config diff_ids
   相符，两端 tar SHA 相同，再经远端真实测试才启用。

来源与精确摘要见 deployment.json 和 amd64.Dockerfile；没有切换到第三方
镜像站、重置密码、关闭校验、升级/重启共享 Docker daemon 或调整其他站点。

## 边界 / not_evidence

- **不是**真实模型/Claude/MCP/Agent Loop 接入，也不是 Product Task/Run 集成。
- Linux 容器共享宿主内核，控制面拥有 Docker 管理权；不是多租户或 VM 级认证。
- 当前仅可信管理员 API，无新前端上传执行页面；不允许经公网执行任意代码。
- 没有新认证系统；未收集用户 Basic 密码，正向公网口令登录未复测。
- 未实现服务 SIGKILL/断电后的自动孤儿回收、取消 API 或失败执行持久审计。
  正常错误/超时有明确返回和清理，不能据此宣称崩溃恢复已经实现。
- 保留合成 smoke 包和成功执行审计，供复核；没有使用业务数据或真实凭据。

## 回退

先关闭各服务 `HARNESS_EXTERNAL_SKILLS`，重新加载 launchd 或 systemd 并重启，
确认执行返回 disabled。原本关闭配置、实际 DB、远端代码/nginx 均有备份，
位置见 deployment.json。恢复代码不得覆盖 `.venv/` 或业务数据；无数据库迁移，
不需要回滚/清空审计 DB。当前没有触发 promotion 后的自动回退路径。
