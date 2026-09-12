# 本地控制面模块

- 先阅读仓库根 AGENTS.md 与 docs/harness/LOCAL_WORKBENCH.md。
- app.py 只处理 HTTP、同源边界和输入转换；业务状态归 service.py 及其 research.py 编排模块。
- store.py 拥有 SQLite 事务；状态、事件和产物发布必须原子提交。
- analysis.py 是固定统计工具，禁止增加 eval/exec/shell 或模型代码执行。
- tools/permissions 常量必须不可变，请求对象不得共享可修改列表。
- Run 终态不可覆盖，重跑创建新 Run；外部配置不允许静默降级。
- 修改契约、失败路径或持久状态后运行 tests/test_workbench.py。
