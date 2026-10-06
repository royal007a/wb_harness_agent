# HA-0088：固定付款评分器纠偏

基线b63847a。只改harness/dsh_payment_eval.py及规格/测试/证据；没有业务运行时改动，不需要为此重启服务，也没有模型调用。

修复三项误计：gold30天时300天也被子串命中；30个工作日单位未比较；失败无产物被记为无例外候选成功。另把结果/标签ID完整性变成前置校验，正确拒绝要求failed/DSH_FINDINGS_INVALID且无发布record。

独立评分仅接受合成脚本固定输出语法，完整匹配数值和单位；不是语义裁判。版本改为dsh-payment-control@2及fixed-script-value-unit@2。中文数字、自由措辞等语法外表达是此评分器不能确认，不宣称生产系统必须拒绝它们。旧报告不重写。

## 验证

最终tests/test_dsh_payment_scoring.py SHA-256：`5d25be458bf380b6cf7bb40d320dc5f966416a5cd2435440ee3e4c21fed292b7`。

- 新36项：36 passed，after-final.xml。
- 同一最终文件，pytest收集前加载b63847a整个旧评分模块：25 failed / 11 passed / 0 errors，before-final.xml。失败为行为断言、未拒绝重复/遗漏ID或错误异常类别；没有模块缺失或导入失败。
- 首轮曾把生产函数verify的哨兵名字写成运行时导入别名verify_findings，产生AttributeError。已修正，并重新完整生成上述基线/修复结果，不把那次算证据。
- 21份现有fixture的ID/单位/gold合法性通过；构造理想的成功/正确拒绝记录验证评分器，不执行SDK。这个测试得到全命中不等于21份合同实际跑成了，也不代表隐含例外真的被识别。
- 网络及生产findings验证器有禁止调用哨兵；score不修改传入records/labels。评测运行流程仍在全部Run完成之后加载labels。

命令：`.venv/bin/python -m pytest -q tests/test_dsh_payment_scoring.py`。

## 单点突变

| 编号 | 变化 | 失败数（其余通过，errors=0） |
|---|---|---:|
| M1 | 完整数值相等改回子串 | 2 |
| M2 | 不比较单位 | 1 |
| M3 | 无需succeeded即可评分产物 | 3 |
| M4 | 跳过ID集合校验 | 7 |
| M5 | 正确拒绝允许仍有发布record | 1 |
| M6 | 无例外候选指标忽略有效成功门槛 | 5 |

每次独立Python进程，在测试导入前对完整模块源码唯一替换后exec；没有修改共享文件。不是全库mutation score。复现辅助代码见replay_plugin.py，设置HA88_MODE=before或M1–M6，再将本目录加入PYTHONPATH并给pytest传`-p replay_plugin`。

## 边界

本提交初次验收时尚未重跑21案例官方SDK链路或真实Provider；本项证明评分器对明确输入判定更严，不证明模型效果提升。当时HA-0085/86冻结版本全量verify仍运行且已见两个失败，不能用这36项通过替代发布门禁。后续21案例实际SDK重跑另见sdk-evaluation-followup.md；不重写初版证据或混称真实Provider验证。独立review待完成，8876/8765/132/正式库未动。

XML只规范化机器路径、主机名和行尾，再重新解析；保留所有失败节点。
