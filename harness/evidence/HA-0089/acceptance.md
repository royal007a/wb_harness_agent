# HA-0089：超时反例先到达被验证阶段

基线d97aef8。只修改tests/test_dsh_runtime.py、规格、计划和证据；生产代码、实际期限、SDK设置、预算和部署不变。

首轮完整verify的失败原文保留在HA-0086/verify-first-failed.log：5秒Run在进入Provider之前已截止，calls=[]。这不是“发送后取消”证据，也不能把calls断言删掉。另一个UI失败发生在page.goto/load阶段；原样单跑1 passed（57.83秒），原因未证实，前端和UI用例未修改。

## 三个到达阶段的反例

真实官方DSH SDK配平台合成Provider，临时SQLite和工作目录，无真实模型、凭据或线上调用。测试Run给SDK初始化留300秒，只有实际进入send_probe后才推进测试局部时钟；生产配置未放宽。

| 边界 | 注入方式 | 期望 |
|---|---|---|
| Run单调截止 | 仅替换dsh_runtime模块的time引用，到达Provider后加301秒 | TIMEOUT |
| 持久Run年龄截止 | 仅替换service模块的datetime引用，到达Provider后加301秒 | TIMEOUT |
| Provider响应期限 | 测试实例的响应期限0.2秒 | DSH_PROVIDER_TIMEOUT |

全部断言：恰好发送一次；从Provider到达起12秒内返回；等待协程被取消；calls=1、spent=0、reserved>0且usage_unknown；无产物、自有run-*目录零残留。不到达Provider仍失败，不跳过。初始化阶段的时间上界由HA-0086另测。

最终测试文件SHA-256：`319461f00b9dfa5215b4dd0145ac34aa3632e4088eb749688c6d78ae388261a4`。

命令：`TMPDIR=/private/tmp .venv/bin/python -m pytest -q tests/test_dsh_runtime.py -k timeout_while_provider`。结果3 passed / 29 deselected（69.78秒），after.xml。

## 独立进程突变

| 编号 | 改变 | 最终结果 |
|---|---|---|
| M1 | 跳过Run单调截止检查 | 1 failed / 31 deselected |
| M2 | 跳过Service持久Run年龄检查 | 1 failed / 31 deselected |
| M3 | 忽略Provider响应期限，只用Run剩余时间 | 1 failed / 31 deselected |

三者均已到达Provider，失败在cancelled.is_set()行为断言；没有导入或初始化失败。失去取消时，合成Provider的pytest.fail还会产生后台线程警告，原样保留，不能当成生产运行异常证据。不是全库mutation score。

mutation_plugin.py在pytest收集前重编译单个方法，不改共享源码。必须保留实际模块globals，否则局部时钟替换会被复制的globals隔离。第一次M1使用了复制globals，其结果不采用；改正后重新跑出的mutation-M1.xml才是最终证据。C2用相同编译路径但不改Service.check代码，1 passed / 31 deselected，证明编译机制没有破坏墙钟注入。运行方式：将本证据目录加到PYTHONPATH，设置HA89_MUTATION=M1/M2/M3/C2并传`-p mutation_plugin`，分别选择对应参数化用例。

## 边界

没有改业务超时逻辑；这是测试阶段和诊断可信度的加固。不能用3项通过替代全量门禁，第二轮完整verify尚待执行。独立复审未完成，不宣称已部署。XML仅替换机器路径和主机名，保持可解析，保留全部失败内容。
