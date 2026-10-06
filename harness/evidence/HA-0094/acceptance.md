# HA-0094 中文条号与偏移验收

基线09caeca；运行实现da56602（当时误编号HA-0093，后续更名HA-0094，不改写提交）。只改共用切块器的中文条号分支和section_start；API/预算/Provider/发布权不变。尚未部署，完整门禁仍有既有UI超时失败。

## 定向结果

- 最终新增21项，另加原切块6项：27 passed（targeted.xml）。四个相关文件：83 passed（related.xml），包括test_chinese_clause_boundaries、test_adaptive_retrieval、test_dsh_payment_findings、test_dsh_ha0079_review_probes。
- 官方SDK配合合成Provider真实读取clause-12，第二轮收到且仅收到第十二条完整文本；两次模型调用、一次工具调用、预留归零、事件不含原文、无工作目录残留。没有真实Provider或生产数据。
- 同一份21项测试使用基线09caeca的adaptive_retrieval模块替换后：20 failed / 1 passed / 0 errors。SDK那项明确是DSH_CLAUSE_NOT_FOUND；不是导入失败。该基线是模块级替换，不声称整棵旧仓库复跑。
- 两个独立定向突变（均不跑SDK）：撤回中文标题分支19 failed/1 passed；恢复重复计算缩进6 failed/14 passed。两个均0 errors，见mutation-heading.xml、mutation-offset.xml；不是全库mutation score。
- 初期SDK探针把read_clause结果当成matches对象（实际普通读取返回列表），造成DSH_GATEWAY_FAILED。两份草稿失败XML保留，修改的是测试协议假设，不是放宽生产校验。它们不能当作产品旧版缺陷。

测试在da56602时SHA256：a707f8dbc6aafa0a489882413d8e498be8c8c97d0412c8324170b35f4c2a4c38。更名只改首行docstring，最终SHA256：36ec363618e71ea9666b5a60fa800c929b1e8c63a1e903f596c9a4f590fe69e5。生产模块SHA256：68a0902e15c2bce69c2ffd38801c334385e24f2ead037f6e713910fd866aa403。

## 评测单独留档

官方SDK+label-blind脚本Provider串行执行原阿拉伯数字21例（payment-eval-arabic.json），再执行只转换行首1..14条号的中文变体21例（payment-eval-chinese.json）。每批77次合成调用；每批11成功、10故意错值拒绝。正确值11/11，错值拒绝10/10，字面例外5/5，无例外4/4，隐含例外仍0/2。

中文变体用evaluate_chinese_variant.py生成，原case与label文件不改；所有Run完成后才读取labels。变体报告包含原输入、变体输入和标签哈希，只记录结果和摘要。两批仅证明固定控制流程没有退化，不证明检索质量或真实模型效果提升。原HA88报告保留。

## 复跑

```sh
env -u ARK_API_KEY -u HARNESS_DSH_REAL_ENABLED -u HARNESS_DSH_CREDENTIAL_REF \
TMPDIR=/private/tmp .venv/bin/python -m pytest -q \
 tests/test_chinese_clause_boundaries.py tests/test_adaptive_retrieval.py \
 tests/test_dsh_payment_findings.py tests/test_dsh_ha0079_review_probes.py
env -u ARK_API_KEY -u HARNESS_DSH_REAL_ENABLED -u HARNESS_DSH_CREDENTIAL_REF \
TMPDIR=/private/tmp .venv/bin/python harness/dsh_payment_eval.py --out /tmp/payment-arabic-new.json
env -u ARK_API_KEY -u HARNESS_DSH_REAL_ENABLED -u HARNESS_DSH_CREDENTIAL_REF \
TMPDIR=/private/tmp .venv/bin/python harness/evidence/HA-0094/evaluate_chinese_variant.py --out /tmp/payment-chinese-new.json
```

需要既有锁定的DSH node_modules。基线复跑方式：在新Python进程导入backend.adaptive_retrieval，读取`git show 09caeca:backend/adaptive_retrieval.py`，用exec(compile(source,module.__file__,'exec'),module.__dict__)替换该模块，再pytest.main运行新文件。突变同样只改该进程模块：一项还原HEADING，一项还原section_start偏移；磁盘生产文件不修改。XML中的源码行显示可能来自当前磁盘文件，断言、异常与统计是该进程实际结果。

## 边界

支持普通中文数字字符集合，不验证数字串是否是合法条号；不支持财务大写、繁体條、条号内部空格。结构识别不防提示注入。长条款仍可能拆成多块，clause-N不等于合同条号。中文以及此前无法正常处理的缩进输入会改变新执行结果，旧Run/产物不重写；没有算法版本持久绑定，也没有跨Run证据续跑。
