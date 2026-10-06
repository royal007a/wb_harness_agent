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

## 原UI文件独立诊断

冻结4b8ec1e，仅运行原来的`tests/test_agent_runtime_ui.py`，使用只读Playwright事件监听记录请求、响应、导航与关闭；原断言和超时没有变更。结果为5 failed / 14 passed，1413.31秒，见ui-network-diagnostic-failed.log。

五处失败不能全部归为导航超时：queued状态、XSS、中文标题mobile三个用例停在page.goto等待load；orphan history停在Exchange ID断言；英文标题mobile停在MODEL_RUNTIME_DISABLED内容断言。两处内容断言当时看到了空区域，是否与前述调度延迟同因仍未证明。

在queued和XSS失败中，静态响应头200先出现，DOM/load事件在较晚时才出现。响应头不证明body已完成，因此继续加入ASGI最后body发送和浏览器requestfinished时序，不能仅凭200排除网络、服务端或浏览器问题。

随后运行四个原用例（`-k 'non_answer_exchange_states or exchange_without_visible_user_message'`），只加ASGI透传计时和上述浏览器监听，4 passed / 15 deselected，159.83秒，见ui-asgi-selected-diagnostic.log。ASGI观察器只包装该UI夹具创建的服务器，保持原receive/send内容。一个成功样本里服务端静态body约0.07秒完成，浏览器DOM/load晚于资源完成；但此轮没有同时复现之前的失败，仍不能宣称找到根因。

## 第四轮正在运行

主worktree固定9f36906（比4b8ec1e只多文档与证据），重新完整运行verify.sh。不使用`-x`，不跳过UI；增加上述两端时序和90秒faulthandler用于诊断，未改断言和测试超时。结果待此进程结束后另记。两次定向诊断的通过项不能抵消失败或代替这次完整运行。
