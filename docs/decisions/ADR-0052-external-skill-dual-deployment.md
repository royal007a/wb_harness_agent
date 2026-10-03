# ADR-0052：外部 Skill 双环境受限启用

日期：2026-10-03。用户授权补齐本机与 118.196.123.132 的镜像和执行配置。

## 决策与契约

- 保留 ADR-0025 的包、输入、输出协议和默认关闭值；仅这两个部署显式开启
  `HARNESS_EXTERNAL_SKILLS=enabled`，不启用模型、网络、MCP 或 Product Run。
- `HARNESS_SANDBOX_BACKEND` 只允许 `colima`（默认，macOS VM）或
  `linux-docker`（显式，固定 unix:///var/run/docker.sock）。不自动回退，不
  接受请求提供的 Docker endpoint/context。Linux 使用宿主内核，不能声称 VM
  或多租户强隔离；Docker daemon 管理权仍是受信任的运维权限。
- `/api/local/external-skills/runtime` 仅 GET 可经现有认证反向代理查看无密
  状态；其他外部 Skill 接口只准直接 loopback/SSH tunnel，拒绝代理标识及
  非回环 peer。nginx 同时禁止公网包读写和执行，不新增认证系统或凭据。
- 保持禁网、非 root、只读根/输入、cap-drop、无凭证/host socket 挂载。
  加上 Docker 日志禁用及宿主流式输出字节上限，防止原始 fd 输出绕过 runner
  的 Python 日志限制；一个服务最多一个执行，忙时拒绝而非无界排队。
- 状态增加 backend、access_scope、max_concurrency；审计记录执行 backend。
  镜像在各架构构建并记录不可变 ID，不能将 Mac 的镜像 ID 当成 Linux 验证。

## 验收与回滚

先本机、后远端：固定 commit、备份实际数据库及部署配置、staging 预检、
构建固定 base digest 镜像、真实容器验证、启用、健康和 API 冒烟。
测试覆盖成功、只读/断网/无凭据、超时、原始输出洪泛和容器清理，以及代理
入口拒绝、非法 backend、默认关闭、幂等和并发。测试只用合成 JSON/脚本。
回滚先关闭 Skill 开关，再恢复已备份代码/配置，不清空任何业务数据库。

非目标：公网任意代码服务、自动执行第三方 Skill、生产级沙箱认证、通用取消
API、真实模型代码生成。进程被 SIGKILL/主机断电后的孤儿容器回收仍属运维
限制，不能把正常异常清理测试描述为崩溃恢复能力。
