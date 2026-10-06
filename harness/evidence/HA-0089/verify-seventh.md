# 第七轮完整门禁：通过

日期：2026-10-07。命令：`sh harness/verify.sh`。退出码 **0**，完整耗时 294.17 秒。

## 固定范围

启动快照为 `1936d9c`，在独立 worktree 中运行。过程中只新增了作者侧课程复核文档并提交为 `63d0c4bfa610f48e237cd51e3677ada04f475b99`；运行代码、测试、规格、验证脚本没有变化。以下路径与主分支当时的 `e25e49c` 无差异：backend、adapters、frontend、tests、dsh-adapter、specs、deploy，以及 harness 根目录下的 Python / shell 脚本。

使用既有 Python venv、DSH/Pi node_modules；未安装或更新依赖。子进程环境移除了 HARNESS_*、API_KEY/TOKEN/SECRET/PASSWORD/CREDENTIAL 类变量、PYTEST_ADDOPTS 和 PYTHONPATH。没有追加筛选、首败退出、跳过 UI、延长测试期限或诊断插件。临时数据库与合成 Provider 不代表真实 Provider 验收。

## 结果

- 完整 pytest：**1852 passed / 22 skipped / 1 warning**，287.27 秒。
- 之后原验证脚本中的三个定向测试依次为 2、2、6 passed；这些是重复范围，不与全量相加。
- 后续离线评测、准入检查、前端与 sidecar 的 Node 语法检查、`git diff --check` 全部正常退出。脚本有 `set -eu`，完整进程最终为 0；不是把独立的分段结果拼接为通过。
- 唯一 warning 是 Starlette 对 anyio BlockingPortal 别名的弃用提示，不是测试线程异常。

完整输出见 `verify-seventh.log`，仅替换个人目录路径。脱敏日志 SHA-256：`d4e38ee87a15bce3b19ac6a9fb646da2f21d70077c0340bc98ce76a5ad89957a`。没有单独生成 JUnit XML；不以本记录冒充未生成的逐用例 XML。

## 并发与结论限制

启动时旧 Claude pytest PID 53051 已退出，但另一轮 PID 58829 已在 Claude worktree 中运行。我没有及时按该检测结果阻止启动，造成测试开始阶段重叠；已在协作消息中更正。验证进程 PID 59447 运行约 131 秒时观察到 58829 已退出，没有终止对方进程。本轮不能称为独占资源验证。

这次完整通过，补齐此前第六轮唯一 UI 失败后的全量绿灯，但**不证明先前 UI 波动的根因已消除**。前六轮失败记录保留，不修改或覆盖。没有对其余 22 个跳过项作已验收声明。

本次没有部署，没有读取 Keychain，没有调用真实模型，没有改动 8876、8765 或远端 132。候选分支 HA-0093 及以后代码不在被测快照中；阅读报告忠实度的独立审查也不由这次门禁代替。主分支的治理状态及发布由其当前负责人在核对证据后更新，本工作区不改共享 tasks/state。
