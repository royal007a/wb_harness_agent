# HA-0092 清理故障隔离

父提交43dd049；第五轮完整验证仍冻结在a5ec114，未修改它的工作树。此次仅适配器清理、规格和离线测试；没有部署或模型调用。

## 证据

- 第五轮堆栈：`test_untrusted_error_envelope_does_not_forward_fields[body4]` 原先抛 DSH_RUNTIME_FAILED，随后finally的 killpg(SIGTERM) 抛PermissionError，将它覆盖。网关和租约释放在异常点之后，因而被跳过。EPERM的操作系统原因未确定。
- 同轮初始化测试得到RUNTIME_FAILED而不是INITIALIZATION_FAILED：只确认现象，不能仅凭相邻失败就判定同因。
- 初版9个集成反例放在未修改的生产代码上：9 failed/0 errors，5.02秒（ha92-before）。均为信号或网关清理故障导致原始异常覆盖/资源未清理，不是导入错误。该版尚未包含之后新增的5个helper级用例，不能声称最终14个在基线原样行为失败。
- 最终新文件14项加原startup16项：30 passed，35.63秒（ha92-final）。Python真实子进程、loopback平台网关和信号故障注入；不是DSH SDK或Provider。
- 最终新测试SHA-256：`2c20085d4fa9cbb603be58d53f6fc4fdf1d74950b6223ee9362a518028bf722f`。
- 5个定向突变各跑13项（排除活进程目录场景）：primary 7失败；success 1失败；lease 8失败；escalate 4失败；pipe 10失败；全部0 errors。它们分别覆盖错误优先级、清理失败不能成功、租约释放、被拒后不继续升级信号、管道释放。不是全库mutation score。

重跑：`.venv/bin/python -m pytest -q tests/test_dsh_cleanup_errors.py tests/test_dsh_startup.py`。突变：将本证据目录加入PYTHONPATH，设置HA92_MUTATION为primary/success/lease/escalate/pipe，pytest加`-p ha92_mutant`，选择新测试文件并`-k 'not denied_live'`。插件只在该测试进程内替换函数，不改源码文件。

## 实现边界

主异常保留，正常返回但发生捕获的清理错误则报固定DSH_CLEANUP_FAILED。子进程信号被拒后停止发送其他终止信号，等待有界；其他资源继续尝试释放。正在运行或权限未知的组使目录保持pending，绝不直接删它。主异常存在时不把清理原文带到事件或响应。

不宣称所有清理异常均被处理：这里只处理OS错误和子进程等待超时，不吞任意编程错误。不解决PGID复用，不承诺所有子进程已死或正文立即消失。后台网关线程原有等待行为不在本次变更范围。

XML和日志仅机械脱敏路径，保留全部failure节点并重新解析。第五轮门禁仍有失败，独立复审及完整验证未通过前不发布。
