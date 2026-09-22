# ADR-0025：第三方外部 Skill 采用不可变包与一次性隔离容器

状态：Proposed（本地受限实现）
日期：2026-09-19

## 背景

Skill 的说明、SDK `allowed_tools`、MCP 过滤和宿主进程内 Hook 都不是不可信代码的 OS 隔离边界。ADR-0024 因而明确禁止加载第三方 Skill；TD-018 也禁止把固定函数线程池当作隔离执行器。

用户要求先补齐可隔离的外部 Skill/工具执行，再建设长期记忆。此决策只定义本地最小执行路径，不批准模型、网络、凭证、动态依赖或把该路径加入任何现有 Claude Run。

## 决策

外部 Skill 包必须是一个严格格式的 ZIP：根目录只能包含 `manifest.json` 与 `entry.py`，manifest 固定 `external-skill-manifest@1`、`python-stdlib@3.12` 和 `transform_json` 单一能力。平台在注册时拒绝路径穿越、链接、额外文件、过大包、无效 manifest 与重复内容摘要；平台将内容复制到受控目录并将 SHA-256 固化到 SQLite。

执行时必须再次验证包内容摘要，并在一次性 Colima Docker 容器运行固定镜像内的固定 runner：

- `/skill` 与 `/inputs` 分别只读挂载；无宿主工作目录、Docker socket、环境变量、网络、凭证或动态安装；
- 非 root、只读根文件系统、所有 capability drop、`no-new-privileges`、CPU/内存/进程/输出/墙钟限制；
- runner 只加载固定的 `/skill/entry.py`，只接受 JSON object，stdout 只能返回一个有大小上限的 JSON object；
- 每一次都创建、执行并强制删除容器；SQLite 写入 package/execution 审计记录，而不是伪装为 Product Run Event。

运行门禁 `HARNESS_EXTERNAL_SKILLS=enabled` 默认关闭。登记包不等于批准执行；本地入口不接受 URL、Git、npm/pip、shell 命令、二进制、依赖清单或任意宿主路径。

## 后果

这条路径可验证“不可信 Python 不在宿主执行、不能联网、没有凭证和不可见宿主文件”的最小安全属性，但不是多租户生产执行器。它仅支持 stdlib JSON transform，尚未与 Product Task/Run、Claude SDK、MCP 或外部工具路由集成。引入新运行时、依赖、挂载、网络或真实资料，必须新 ADR、供应链审计和 L3 探针。
