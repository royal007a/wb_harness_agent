# 外部 Skill 隔离运行时

状态：ADR-0025 Proposed 的本地受限实现。此能力是受限 JSON 转换执行器，不是 Claude SDK、MCP、模型工具、通用插件市场或多租户生产沙箱。

## 可以做什么

本机可信管理员可上传一个不超过 128 KiB 的 ZIP，再由工作台在一次性 Colima Docker 容器内运行其固定 `entry.py`。包必须只包含两个根文件：

```text
manifest.json   # external-skill-manifest@1
entry.py        # export main(payload) -> JSON object
```

manifest 固定为 `python-stdlib@3.12`、`entry.py`、`transform_json`；不接受包内依赖、命令、二进制、链接、目录、额外文件或任何动态安装。登记时平台复制内容到受控目录并记录内容 SHA-256；每次执行前再次复核摘要，因此登记后的文件漂移会拒绝而非执行。

`POST /api/local/external-skills/packages?source_label=<label>` 使用 `application/zip` 和 `Idempotency-Key` 登记包。`POST /api/local/external-skills/packages/{package_id}:execute` 接收严格 JSON：

```json
{"input": {"value": "example"}}
```

两者及状态/列表接口的机器契约见 [`external-skill-runtime.schema.json`](../../specs/v1/external-skill-runtime.schema.json)。本地 OpenAPI 端点也会动态暴露这份 Schema。

## 强制隔离 profile

`external-skill-stdlib-v1` 使用固定、按摘要解析的 `harnessagent-external-skill:0.1` 镜像和固定 runner：

- `/skill` 与 `/inputs` 只读挂载；无仓库、用户目录、Docker socket、宿主环境变量或长期凭证；
- 容器禁网、非 root、只读根文件系统、`cap-drop=ALL`、`no-new-privileges`；
- CPU 0.25、内存/交换 128 MiB、24 个进程、64 文件描述符、1 MiB 文件输出、8 MiB 临时盘和最长 10 秒；
- runner 只能加载 `/skill/entry.py`，只读取 JSON object，stdout 只能输出一个不超过 24 KiB 的 JSON object；第三方日志和堆栈不会回传 API；
- 每次执行新建并强制删除容器，审计保存 package/input/output 摘要、镜像/profile 摘要、时长和清理状态。

开发或镜像变更后，使用以下命令构建并运行真实 Colima 探针：

```sh
docker --context colima build -f sandbox/external-skill.Dockerfile -t harnessagent-external-skill:0.1 sandbox
HARNESS_DOCKER_TESTS=1 .venv/bin/python -m pytest -q tests/test_external_skills.py
```

## 门禁与非目标

`HARNESS_EXTERNAL_SKILLS=enabled` 默认**未设置**。因此执行接口先返回 `EXTERNAL_SKILL_RUNTIME_DISABLED`，不会读取登记包或启动 Docker。注册包也不会执行包内代码。

该运行时不允许 URL、Git、pip/npm、shell、任意宿主路径、网络、凭证、模型、MCP、真实资料或 Product Task/Run 自动接入。它的独立 audit 记录不假装为 Product Event；将来接入一个 Product Run 时，必须先定义 Task/Run/权限/预算/审批关联与新的 ADR。容器隔离是本机单用户 L3 探针，不等价于多租户、内核级或生产供应链认证。
