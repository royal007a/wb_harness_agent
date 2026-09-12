# 引擎与 VM 探针

本地固定分析器已通过独立 Adapter 生命周期运行。Run 排队时绑定描述符摘要，版本漂移拒绝执行；适配器不能发布终态，结果需经平台验证，清理失败不得成功发布。

## 可复现命令

前提：本机已运行 Colima VM 的 Docker context；以下步骤安装可选 SDK、拉取固定基础镜像并构建本项目镜像，不改业务数据。

```sh
.venv/bin/python -m pip install -r requirements-agent.txt
docker --context colima build -t harnessagent-sandbox:0.1 sandbox
.venv/bin/python harness/probe.py
```

探针创建短生命周期容器，只挂载专属 CSV 输入目录，非 root、禁网、只读根、cap-drop ALL、no-new-privileges、256 MiB、0.5 CPU、32 PID；每个步骤最多 60 秒，输出最多 128 KiB。只销毁该探针持有的容器 ID，不清理其他工作负载。

输出：[probe.json](../../harness/evidence/HA-0007/probe.json)、[JUnit](../../harness/evidence/HA-0007/probe-tests.xml)。记录镜像 ID、配置摘要、SDK 版本、时间与测试数量。

`GET /api/v1/readiness` 只读历史证据并核对配置/SDK 摘要；不启动容器、不调用模型，不承诺 Docker 当前健康或镜像标签仍指向同一镜像。修改镜像、Runner、运行参数或 SDK 后必须重新探测。

## 实际验证范围

- 真实 Colima VM 容器中的状态保持、只读挂载、非 root、禁网、宿主路径/socket/环境变量隔离；
- 步骤超时、运行中取消、异常输出以及销毁；
- Smolagents 1.26.0 的真实 CodeAgent 循环，通过显式 PythonExecutor 执行容器代码；
- 明示脚本模型的多轮调用、错误恢复、预算耗尽时拒绝额外 fallback；
- 确定性 Skill 脚本的聚合、溯源和输出保护。

没有调用真实语言模型；探针响应为预先定义的测试程序，不能作为自然语言分析效果证据。SDK 模型调用、网络取消、Token/成本限制与生产适配器验收未完成，真实引擎路由仍关闭。Colima 的容器隔离测试也不等于生产安全认证或硬件侧信道审计。

恢复下一阶段需要用户提供批准的模型端点、模型 ID、凭证的本地配置引用和费用上限；不要把密钥发到聊天或提交仓库。不得使用其他项目的凭证，也不静默回退引擎。
