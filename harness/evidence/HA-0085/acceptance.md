# HA-0085：票据退役语义与终态事务

状态：代码待独立复审；发布门禁未通过，未部署。基线 77573ee（运行时代码与5939e5d一致）。

## 变更

- issued→retired，不把未使用票据当作 Provider 失败；in_flight→unknown 不变。
- 新事件 data.schema_version=dsh-crossing@2；历史 failed 不改写。
- 正常成功/失败：本 generation 退役与终态在同一个事务中，退役后重读 Run 保证 sequence 连续。
- 终态事务失败时，不在 finally 对仍为 running 的 Run 单独提交退役；启动恢复处理。取消不等 Provider，迟到 unknown 仍可追加。
- 不改变工具集合、模型路由、调用次数、预算和准入；不修改 DSH SDK 依赖。

## 可复核证据

运行环境：Python3.14；已有固定版本依赖通过本地 symlink 复用；所有 DB 和工作目录均为临时路径。没有真实 Provider 请求，也没碰8876/8765/132。

1. `before.xml`：运行时代码用 apply_patch 临时还原，`git diff --exit-code -- backend/dsh_crossings.py backend/dsh_runtime.py` 确认与77573ee逐字一致；首版十条最终修正后的测试得到 **8 failed / 2 passed / 0 errors**。失败为 retired 状态、正常终态顺序、终态事务故障后的独立退役等行为断言，不是导入错误。
2. 修复后首版十条测试曾 **10 passed**。随后补一条不依赖 SDK 启动的 controlled_bridge 测试；`controlled-bridge.xml` 为 **1 passed / 10 deselected**。当前完整新文件是11项，不将前十项记录冒充十一项全过。
3. `targeted-initial.xml`：新文件当时十项 + crossing旧测试 + HA82探针 + workbench，**95 passed / 2 failed**；两项失败单独复跑 `targeted-recheck.xml` 为 **2 passed**。首轮失败仍保留。
4. `after.xml`：新增 controlled_bridge 后，完整11项 **10 passed / 1 failed**，失败为 free 模板 SDK 启动前失败，并非完成事务。没有将这一轮写成全过。
5. `mutations.json` 和 M1–M8 XML：8个定向突变均被测试捕获，全部errors=0。只跑对应1–2项，不是全套 mutation score。
   - M1未使用改回failed，M2未知改为retired，M3跨代次清理，M4删事件版本区分，M5终态故障后独立finally提交，M6失败退役移回finally，M7成功退役移回finally。
   - M8不重读Run造成旧sequence写入：SDK两个参数中 free 还遇到了独立启动失败，payment已完成3次模型调用后在发布阶段失败。因此追加不依赖SDK启动的 `M8-controlled.xml`：两次平台模型回调完成，终态仍错误地失败，测试捕获。不能把启动失败算成M8有效证据。
6. `deterministic.xml`：最终文件中不需要 SDK 启动的7项 **7 passed / 4 deselected**。最终测试文件 SHA-256：`e7052d7829812223a76cdafb8092213cdb0f912cb710187bbf6514bbb46c5aef`。

## 尚未通过的 SDK 启动门禁

诊断时仅在本隔离worktree短暂打开合成运行的 stderr，随后撤销并确认 bridge.mjs 无差异。独立抓到固定 SDK 错误：`initialize timed out after 20000ms waiting for dsh profile "sdk-minimal"`。对应失败Run没有 model.completed、没有模型发送；原先只暴露 DSH_RUNTIME_FAILED，掩盖了启动阶段。

这不是由retire事务触发，但也是本机当前真实存在的可用性问题，不以“重跑变绿”视为解决。将启动期限与固定错误分类拆为后续原子任务，继续受Run总截止控制；不为此重试模型、不释放unknown预算。全量verify与部署必须在明确处理后重新执行，本提交尚未宣称通过。

## 测试脚手架更正

最早一次直接调用pytest入口导致backend导入失败，改为 `.venv/bin/python -m pytest`。后续发现默认macOS临时目录有符号链接，改用解析后的短临时根；另有新增event拦截器漏接step_id位置参数，已经修正。以上早期环境/脚手架失败不计为基线行为反例；before.xml 是修正后重新生成的版本。

重跑：`TMPDIR=/private/tmp .venv/bin/python -m pytest -q tests/test_dsh_crossing_retirement.py tests/test_dsh_crossings.py tests/test_dsh_ha0082_review_probes.py tests/test_workbench.py`。

## 边界

取消后审计并不保证run.cancelled为最后一条；实际调用与收据仍不保证跨外部Provider exactly-once。未知预算冻结保留；历史事件没有重写。XML仅机械替换机器名与本机路径，结构解析检查通过；课程正文、秘密、生产DB均未纳入证据。
