# HA-0028：可隔离外部 Skill 执行切片

## Objective

建立默认关闭、可审计的外部 Skill ZIP 登记与一次性隔离执行纵向切片，解除“只能用文档约束外部 Skill”的缺口；不将外部 Skill 接入模型或真实投研 Run。

## Scope

1. 固定 package manifest、注册、执行结果的机器契约与供应链摘要。
2. ZIP 内容检查、不可变受控落盘、摘要复核、SQLite package / execution 审计和幂等语义。
3. Colima 一次性容器 profile：禁网、非 root、只读挂载/根文件系统、资源限制、固定 runner、强制清理。
4. 默认拒绝门禁、异常/超时/污染输出、摘要漂移和真实隔离探针测试。

## Non-goals

- 不接受 URL、Git、pip/npm、shell 命令、动态依赖、二进制或任意宿主路径。
- 不赋予网络、秘密、模型、MCP、Claude SDK 或 Product Task/Run 权限。
- 不把本地单用户容器证明为多租户生产隔离。

## Acceptance

- 默认 gate 在 Docker/包读取前拒绝执行；注册不执行包内代码。
- 已登记 ZIP 的 digest 固化且漂移拒绝，entrypoint 只能在固定镜像的一次性禁网非 root 容器运行；每次均有可追溯审计和清理。
- L2 契约/安全/故障测试通过；可用 Colima 环境额外通过真实容器的主机不可见、禁网与输出边界探针。
