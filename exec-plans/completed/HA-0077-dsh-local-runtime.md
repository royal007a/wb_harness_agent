# HA-0077：两小时 DSH 分支与本地部署

开始：2026-10-05T10:32Z；目标时间窗至12:32Z。

1. 固定官方 DSH0.2.1-alpha.1（阅读源码5badb15），安装独立依赖，验证SDK实际启动。
2. 显式窄profile与工具/模型网关；平台Run持久化和结果发布，受控退出。
3. 独立页面及本地服务（新端口/数据库），覆盖安全与生命周期回归。
4. 实际部署、浏览器验证、提交证据并交mymacclaude review；不改原工作台/远端。

未完成部分不声称完成；遇凭据或系统隔离阻塞仍先推进其余实现和可复核离线证据。

## 完成记录（2026-10-05）

- 官方 SDK + 平台 Provider/工具桥、输入/预算/取消/超时、目录崩溃回收、元数据事件、真实模式显式选择均落地。
- 独立8876当前登录会话部署；真实豆包合成合同2次请求1795Token、合成联调和两套页面浏览器验证通过。
- d813b63 代码获 mymacclaude Approved。另加两个定向用例，生产代码未变；最终验证见 HA-0077/verify-final.log，包含全量与既有评测、静态检查。
- 保守边界和非目标见 docs/harness/DSH_LOCAL_RUNTIME.md、tech-debt-tracker.md；未合并main、未发布8765/132。
- 证据入口：harness/evidence/HA-0077/acceptance.md。最终发布身份/重启回读由 deploy/verify_dsh_local.py 核对，运行时回执输出 .local/dsh-deployment-final.json（不向Git写入运行库）。
