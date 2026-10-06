# HA-0092 清理故障隔离

父提交43dd049；第五轮完整验证仍冻结在a5ec114，未修改它的工作树。此次仅适配器清理、规格和离线测试；没有部署或模型调用。

## 证据

- 第五轮堆栈：`test_untrusted_error_envelope_does_not_forward_fields[body4]` 原先抛 DSH_RUNTIME_FAILED，随后finally的 killpg(SIGTERM) 抛PermissionError，将它覆盖。网关和租约释放在异常点之后，因而被跳过。EPERM的操作系统原因未确定。
- 同轮初始化测试得到RUNTIME_FAILED而不是INITIALIZATION_FAILED：只确认现象，不能仅凭相邻失败就判定同因。
- 初版9个集成反例放在未修改的生产代码上：9 failed/0 errors，5.02秒（ha92-before）。均为信号或网关清理故障导致原始异常覆盖/资源未清理，不是导入错误。该版尚未包含之后新增的5个helper级用例，不能声称最终14个在基线原样行为失败。
- e64b03d版新文件14项加原startup16项：30 passed，35.63秒（ha92-final）。Python真实子进程、loopback平台网关和信号故障注入；不是DSH SDK或Provider。
- e64b03d新测试SHA-256：`2c20085d4fa9cbb603be58d53f6fc4fdf1d74950b6223ee9362a518028bf722f`。
- 5个定向突变各跑13项（排除活进程目录场景）：primary 7失败；success 1失败；lease 8失败；escalate 4失败；pipe 10失败；全部0 errors。它们分别覆盖错误优先级、清理失败不能成功、租约释放、被拒后不继续升级信号、管道释放。不是全库mutation score。

重跑：`.venv/bin/python -m pytest -q tests/test_dsh_cleanup_errors.py tests/test_dsh_startup.py`。突变：将本证据目录加入PYTHONPATH，设置HA92_MUTATION为primary/success/lease/escalate/pipe，pytest加`-p ha92_mutant`，选择新测试文件并`-k 'not denied_live'`。插件只在该测试进程内替换函数，不改源码文件。

## 实现边界

主异常保留，正常返回但发生捕获的清理错误则报固定DSH_CLEANUP_FAILED。子进程信号被拒后停止发送其他终止信号，等待有界；其他资源继续尝试释放。正在运行或权限未知的组使目录保持pending，绝不直接删它。主异常存在时不把清理原文带到事件或响应。

不宣称所有清理异常均被处理：这里只处理OS错误和子进程等待超时，不吞任意编程错误。不解决PGID复用，不承诺所有子进程已死或正文立即消失。后台网关线程原有等待行为不在本次变更范围。

XML和日志仅机械脱敏路径，保留全部failure节点并重新解析。第五轮门禁仍有失败，独立复审及完整验证未通过前不发布。

## 交审后自审修订

e64b03d用sys.exception()判定主异常，会误看到调用方except中的无关异常。补入`test_success_with_cleanup_fault_is_not_success[True]`后，e64b03d为1 failed/1 passed（ha92-outer-before），失败点是没有抛出应有的DSH_CLEANUP_FAILED。现改成本次run显式operation_failed标记，不读外层异常状态。

最终15项加原startup16项：31 passed，22.95秒（ha92-followup）。测试SHA-256：`5454cf19cd65813fd6b417b36ea59a7b1ea78fab122c181495a20bd6c7c02524`。之前14项/30通过和5个突变保留为历史结果，不覆盖改写。

修订后5个突变重新运行，每个14项、排除活目录用例：primary 7失败、success 2失败、lease 9失败、escalate 4失败、pipe 11失败，全部0 errors（ha92-followup-*.xml/log）。

实际系统探针 owned_signal_probe.py：只启动并发送信号给本脚本创建的20个短命子进程。在当前macOS上17次信号返回EPERM，随后wait返回0；3次信号成功，wait返回-15。它证明短命子进程场景可以出现EPERM，不证明内核原因或PID复用，也不涉及DSH/Provider。首次未记录wait返回值的探针是18次EPERM/2次成功，不能混为同一次结果。

## 第五轮完整门禁

a5ec114：3 failed/1804 passed/22 skipped，3229.81秒，verify-fifth-failed.log。失败是聊天UI早EOF场景的发送前会话选择，以及两个startup错误分类用例。verify.sh因pytest失败退出，后续命令没有执行。

UI诊断：详情GET在浏览器记录request后约0.087秒被标记ERR_ABORTED，ASGI完整处理约0.896秒并返回200；尚未发送消息。不得把这个错误称为模型/SSE业务失败。保持原测试不变，隔离运行1 passed/55.32秒（ui-fifth-isolated），不能据此宣称根因修复。浏览器调度、请求传输与5秒详情期限的精确先后仍未建立。

## 第六轮完整门禁

固定3036543：1 failed / 1821 passed / 22 skipped，2230.42秒，exit 1（verify-sixth-failed.log）。唯一失败是聊天UI取消态会话按钮的30秒点击超时，不是本轮DSH断言失败；这仍不能豁免整体门禁。两个startup错误分类用例本轮通过，不能据此证明上轮全部根因相同。

pytest之后的verify步骤在同一固定源码上单独运行，exit 0（verify-sixth-post-pytest.log）；不拼接成完整verify通过。完整命令和UI诊断边界见[后续验证](../HA-0089/full-verification-followup.md)。未发布，仍待独立复审。

## 浏览器内时钟定向观察（不是修复验收）

在同一3036543上，对原`non_answer_exchange_states`三个参数化用例加只读计时探针，3 passed / 16 deselected，60.07秒（ui-clock-diagnostic.log/xml）。原断言、点击期限和请求路径都未改。探针见ui_clock_diag.py；重用前述网络/ASGI透传观察器之外，新增浏览器100ms定时器、会话按钮指针/点击时间、Resource Timing，以及Python线程100ms心跳。不记录页面正文。

三个通过样本中浏览器定时器最大间隔分别约4.386、2.212、3.300秒；Python线程对应最大间隔约0.280、0.259、0.475秒。这显示通过时也有浏览器侧可见的延迟，但不能据此确定是页面长任务、调度还是其他因素；没有采集Long Task/CPU profile，也没有在同一探针下复现30秒点击失败。观察器会带来额外开销，不能把它的通过替代原完整验证，不能认定根因已修。

核心时钟探针可独立复跑：把本证据目录加入PYTHONPATH，运行`.venv/bin/python -m pytest -q -s -p ui_clock_diag tests/test_agent_runtime_ui.py -k non_answer_exchange_states`。日志中的原网络/ASGI诊断来自本轮私有观察器，不把缺少它们的复跑称为逐字节相同环境。
