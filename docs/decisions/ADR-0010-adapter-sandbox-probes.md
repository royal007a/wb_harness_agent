# ADR-0010：引擎边界与本地 VM 沙箱接入

状态：Accepted（开发接入与探针范围）；日期：2026-09-12。

用户批准继续“统一引擎契约 → 模型与隔离沙箱验证 → Smolagents CodeAgent”路线。现有 Colima Docker VM 可用；本项目进程尚未配置模型端点或凭证。

本阶段先把固定分析器移到显式适配器接口，增加模型就绪信息和可复现沙箱探针。固定 Smolagents 1.26.0，使用 SDK 原生 CodeAgent 循环与自定义 PythonExecutor；禁止默认回落本地 PythonExecutor。SDK 宿主仅生成代码和转换消息，代码由 Colima VM 内的受限容器执行。

沙箱镜像使用固定 Python stdlib 与 JSON 行协议 Runner，非 root、禁网、只读根、cap-drop ALL、no-new-privileges、CPU/内存/PID/文件描述符限制；唯一宿主挂载是该次登记输入的只读目录，输出用有界 JSON 返回。无宿主 socket、无密钥、无 pickle。每 Run 一容器保持代码变量，退出前销毁；残留清理只针对本项目容器标签和 ID。

后续首个目标驱动场景收敛到可确定性验证的分组聚合：按一个字段分组，对数值列做 sum/mean/min/max/count。目标为 Agent 提交结构化结果，控制面独立回算后生成报告和安全 SVG。HA-0007 当前只验证 SDK 固定样例与独立 Skill 聚合 CLI，不宣称这一真实模型产品链路已经完成。任意自定义分析/图片仍不在本切片验收范围。

在没有已批准模型连接前，仅用明示的脚本模型完成 SDK/沙箱契约探针；不得把它呈现为真实模型效果。模型配置、价格、Token 上限和端点仍需单独实际验证，生产 CodeAct 准入保持关闭。

来源：[Smolagents Agents](https://huggingface.co/docs/smolagents/reference/agents)、[安全执行](https://huggingface.co/docs/smolagents/tutorials/secure_code_execution)、[Docker 资源和权限参数](https://docs.docker.com/engine/containers/run/)。
