# 完整验证后续结果

固定运行代码4b8ec1e；后续课程文档在独立worktree编写，不改变被测源码。所有运行均去掉ARK_API_KEY、HARNESS_DSH_REAL_ENABLED和HARNESS_DSH_CREDENTIAL_REF，使用临时DB；未触碰在线服务。

## 第二轮未完成

`sh harness/verify.sh`在UI阶段出现两个F后，由操作者中断，最终进程退出143。输出仅有155个方法、23个feature的inventory检查和pytest点号，见verify-second-interrupted.log。收集顺序指向最先两个UI用例，但没有取得实际异常栈，不能报告其具体根因或将它计成完整全量结果。

中断后的pytest清理未退出，采样看见greenlet路径；随后只终止本轮拥有的Playwright driver和pytest进程，没有重启8876或其他服务。这不是测试通过，也不是生产故障证据。

保留前序29项加首个UI的独立诊断，30 passed（71.59秒）。此诊断没有改原断言或超时，不证明完整收集环境下的失败已消除。

## 第三轮首败退出

命令仍为`sh harness/verify.sh`，附加`PYTEST_ADDOPTS='-x -o faulthandler_timeout=90'`和仅即时输出失败栈的私有插件；没有跳过任何已选择测试。首败即结束，因此verify后续命令未运行。

结果：1 failed / 37 passed，600.96秒，exit 1。`test_exchange_without_visible_user_message_is_not_lost`在page.goto等待load时30秒超时，还没有执行选择会话与内容断言。完整失败栈见verify-third-failed.log。faulthandler的90秒堆栈只是诊断，不另算一次测试失败。

前端、app和该UI测试文件在5939e5d..4b8ec1e无差异；这不能单独排除间接影响，但没有证据支持通过修改断言、跳过UI或延长导航期限来解决它。正在用原19项UI加只读请求时序监听诊断。主机负载较高只是观察，不认定为根因。

发布门禁仍未通过。HA89定向三项通过、前序30项通过、首轮1754项通过分别是不同范围和版本，不能拼接成一个不存在的完整绿灯。

日志仅机械替换本机用户名和解释器路径，保留失败内容。没有课程全文、密钥、真实合同或生产DB。
