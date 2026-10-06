# UI 当前状态对照（2026-10-07 07:19 CST）

不是完整发布门禁，也不是宣称历史失败已修复。

先做未加载业务代码的随机loopback空白页面控制组（browser_control.py）：Chromium启动0.599秒；三次HTTP读取0.015/0.001/0.001秒；goto为0.034/0.011/0.007秒，点击0.434/0.045/0.049秒，evaluate均小于0.004秒。没有修改浏览器默认期限或停止其他应用。此时采样swap占用仍约18.7GB，仅凭占用量不能推断实时调度延迟。

随后原test_agent_runtime_ui.py全部19项，使用只读ASGI/network/work诊断，原断言/期限不变：19 passed，25.93秒，XML和完整诊断日志随附。相比此前500–1400秒并出现超时的隔离UI运行，这是当前观测变化，不是修复提交。

开始运行时HEAD为bc30e79，运行期间另一路同bot会话提交b49f43b（11份文档/治理文件）。已用git diff核实两提交之间backend/adapters/frontend/tests/verify无差异；不把被测治理快照说成完全冻结。未触碰8876/8765/132、真实Provider或生产DB。

命令：

```sh
env -u ARK_API_KEY -u HARNESS_DSH_REAL_ENABLED -u HARNESS_DSH_CREDENTIAL_REF \
PYTHONPATH=<private-diagnostic-plugins>:. TMPDIR=/private/tmp \
.venv/bin/python -m pytest -q -s -p ui_asgi_diag -p ui_network_diag -p ui_work_diag \
tests/test_agent_runtime_ui.py --junitxml=/tmp/ui-current-bc30e79.xml
```

结论：当前空白页及独立UI均能及时响应。没有同一负载下的失败对照，不能由此将历史失败归因于主机、排除偶发应用问题，或拼接出全量通过。未启动新的完整verify，避免与另一并发会话重复占用资源；第六轮完整门禁的1 failed仍然有效。诊断脚本随附以便复核，未加入正式测试门禁。
