# HA-0091：取消/崩溃探针阶段同步

父提交19554c2，生产运行代码仍为4b8ec1e；本项没有生产代码变更。最终tests/test_dsh_runtime.py SHA-256：`bfe84229328f02307477d169c607d125232a07f838b88370360d1791dac857ed`。

第四轮完整门禁在取消started.wait(10)、崩溃reached.wait(20)处失败，均未进入要测的故障阶段；另外intent子进程5秒超时。旧取消探针设置失败后还泄漏线程，随后产生closed database警告。原始失败经路径脱敏保存在HA-0089/verify-fourth-failed.log，不改写为通过。

改动：设置等待75秒，运行期限300秒只用于合成测试。取消探针在进入Provider后明确保持挂起，再取消，另要求12秒内线程退出、Provider协程收到取消；finally释放测试挂起并回收线程。调用行unknown和预算根cancelled是不同状态，逐个验证；未知usage不解冻预留。终态不发布、目录清理、重复execute不新增调用都有断言。SIGKILL探针仅延长进入第二次请求的设置等待，正文落盘、kill后退出、恢复清理断言不变。

## 独立结果

- 两个修订用例及未修改的intent原用例：3 passed，36.07秒，after.xml/log。intent单项0.702秒；未修改它的5秒限制。
- M1移除runtime.cancel：1 failed，34.84秒；在Provider已经到达后的线程退出断言失败，不是设置或导入失败。
- M2从预算调用监视中移除cancel_event：1 failed，52.22秒；同样在Provider到达后的线程退出断言失败。收尾时网关出现BrokenPipeError，一并保留，不算额外缺陷修复。
- C1对实际SDK适配器人为增加11秒启动延迟：1 passed，51.84秒。实际SDK仍执行，不用假桥绕开初始化。

突变仅在独立进程中用monkeypatch，不改共享生产文件。复跑：将本目录加入PYTHONPATH，指定HA91_MUTATION=M1、M2或C1，pytest加`-p mutation_plugin`并选择`tests/test_dsh_runtime.py::test_cancel_while_provider_waits_never_publishes`。普通复跑不加载插件。

XML仅机械替换路径与主机名，重新解析；没有删除失败节点。不声称三个探针通过就是完整门禁通过。第五轮完整验证、独立review与发布仍待完成；8876、8765、132和真实Provider均未动。
