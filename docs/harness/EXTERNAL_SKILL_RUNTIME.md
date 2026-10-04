# 外部 Skill 隔离运行时

状态：ADR-0025 Proposed 的本地受限实现。此能力是受限 JSON 转换执行器，不是 Claude SDK、MCP、模型工具、通用插件市场或多租户生产沙箱。

HA-0052 / [ADR-0052](../decisions/ADR-0052-external-skill-dual-deployment.md)
补充双环境显式部署：默认代码开关仍关闭；批准的本地 plist 与远端 systemd
drop-in 开启外部 Skill。`HARNESS_SANDBOX_BACKEND=colima` 使用本机 VM，
`linux-docker` 显式使用 Linux 的 `/var/run/docker.sock`，禁止自动回退。
后者共享宿主内核，不具备 Colima 的额外 VM 边界。

公网只开放 `GET /api/local/external-skills/runtime` 状态（沿用现有 Basic
认证），包列表/上传/执行只允许直接 loopback 或 SSH 隧道；nginx 与应用层
都拒绝代理访问这些接口。没有新增 HTTP 身份系统或公网任意代码执行能力。
远端使用方式：`ssh -N -L 18765:127.0.0.1:8765 root@118.196.123.132`，然后
对 `http://127.0.0.1:18765/api/local/external-skills/` 发本机 API 请求。

## 可以做什么

本机可信管理员可上传一个不超过 128 KiB 的 ZIP，再由工作台在一次性 Colima Docker 容器内运行其固定 `entry.py`。包必须只包含两个根文件：

```text
manifest.json   # external-skill-manifest@1
entry.py        # export main(payload) -> JSON object
```

manifest 固定为 `python-stdlib@3.12`、`entry.py`、`transform_json`；不接受包内依赖、命令、二进制、链接、目录、额外文件或任何动态安装。登记时平台复制内容到受控目录并记录内容 SHA-256；每次执行前再次复核摘要，因此登记后的文件漂移会拒绝而非执行。

HA-0073明确ZIP方法仅支持无加密stored/deflated，继续限制每个文件64KiB；
损坏压缩流、非法UTF-8、manifest解析上限均按输入错误拒绝。登记与列表等四入口
的HTTP合同和故障验证见`specs/testing/EXTERNAL_SKILL_HTTP_CONTRACTS.md`。

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
- Docker 日志驱动关闭，宿主流式捕获 stdout 上限 32 KiB（runner 合法 JSON
  上限仍 24 KiB），stderr 不回传；每个服务最多一个执行，忙时 429，无无界队列。
- runtime 返回 `backend`、`access_scope` 和 `max_concurrency`；执行审计增加
  `backend`。SHA 固定到实际架构镜像，不复用其他机器的探针作验证证据。

开发或镜像变更后，使用以下命令构建并运行真实 Colima 探针：

```sh
docker --context colima build -f sandbox/external-skill.Dockerfile -t harnessagent-external-skill:0.1 sandbox
HARNESS_DOCKER_TESTS=1 .venv/bin/python -m pytest -q tests/test_external_skills.py
```

## 门禁与非目标

`HARNESS_EXTERNAL_SKILLS=enabled` 默认**未设置**。因此执行接口先返回 `EXTERNAL_SKILL_RUNTIME_DISABLED`，不会读取登记包或启动 Docker。注册包也不会执行包内代码。

上句指新执行：同key同请求仍可回放历史成功收据，不读取包、不新执行。runtime/
列表查询会做镜像可用性探测，可调用Docker CLI，但不启动容器；不能称零I/O。
DB回滚可能留下按摘要固化的文件目录，重试复核后复用。容器执行之后DB失败，
再次请求可能重新执行；不承诺跨文件系统/容器/DB的exactly-once。

该运行时不允许 URL、Git、pip/npm、shell、任意宿主路径、网络、凭证、模型、MCP、真实资料或 Product Task/Run 自动接入。它的独立 audit 记录不假装为 Product Event；将来接入一个 Product Run 时，必须先定义 Task/Run/权限/预算/审批关联与新的 ADR。容器隔离是本机单用户 L3 探针，不等价于多租户、内核级或生产供应链认证。

正常退出/异常/超时清理已测试；宿主强杀或断电后没有持久孤儿容器回收器，
运维须核对标签 `local.harnessagent.external-skill=true` 的遗留实例，不能将
这种场景当成已经实现的自动恢复。回滚先关闭开关，恢复部署备份，不删业务 DB。

远端不能访问 Docker Hub 时，可在本机用同一 Dockerfile/base digest 构建
`--platform linux/amd64`，通过 `docker save` → SSH → `docker load` 传输。
发布脚本的显式 `HARNESS_PREBUILT_EXTERNAL_IMAGE=sha256:...` 要求远端 tag
解析的镜像 ID 和 Linux/amd64 架构匹配；仍在远端重跑真实隔离测试，不能用
本机测试代替。普通发布未提供该值时仍按固定 Dockerfile 构建。
