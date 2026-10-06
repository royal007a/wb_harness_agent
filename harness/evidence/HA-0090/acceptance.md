# HA-0090 中文条号与偏移验收

基线09caeca；初版运行实现da56602（历史误用HA93/94，最终编号为此前预留的HA90，不改写提交）。初版只改共用切块器的中文条号分支和section_start；返工另修跨块例外候选，见末节。API/预算/Provider/发布权不变。尚未部署，完整门禁仍有既有UI超时失败。

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
TMPDIR=/private/tmp .venv/bin/python harness/evidence/HA-0090/evaluate_chinese_variant.py --out /tmp/payment-chinese-new.json
```

需要既有锁定的DSH node_modules。基线复跑方式：在新Python进程导入backend.adaptive_retrieval，读取`git show 09caeca:backend/adaptive_retrieval.py`，用exec(compile(source,module.__file__,'exec'),module.__dict__)替换该模块，再pytest.main运行新文件。突变同样只改该进程模块：一项还原HEADING，一项还原section_start偏移；磁盘生产文件不修改。XML中的源码行显示可能来自当前磁盘文件，断言、异常与统计是该进程实际结果。

## 边界

支持普通中文数字字符集合，不验证数字串是否是合法条号；不支持财务大写、繁体條、条号内部空格。结构识别不防提示注入。长条款仍可能拆成多块，clause-N不等于合同条号。中文以及此前无法正常处理的缩进输入会改变新执行结果，旧Run/产物不重写；没有算法版本持久绑定，也没有跨Run证据续跑。

## 跨块例外返工

独立复现：第一条含付款期限，第二条只有“发生质量争议时，期限延期”，初版正确切成两块后，原同块共现词表不再报告第二块。这是真实门禁退化，不能以切块单测通过掩盖。

已在规格先增加同一付款文档内的保守候选，再改candidates。新增6项修前4失败/2通过，见coverage-before.xml；修后包含前述四文件及新文件共89 passed，见coverage-related.xml。SDK路径证明首次提交得到COVERAGE_GAP，读第二块、重新提交后才通过。没有付款词、没有例外词和无关争议的保守误报都分别测试；不宣称语义判断。

原两套21例JSON属于da56602初版，不能作为返工后评测；返工评测另存。当前测试文件仅因HA编号调整了docstring，旧SHA是当时被测文件，不冒充当前SHA。完整门禁与独立复审仍未完成。

48d32c7返工后两套评测已另存payment-eval-revised-{arabic,chinese}.json，各21例，均发生相同退化：正确值发布10/11、字面例外4/5，其余指标不变。long-01从成功改为DSH_FINDINGS_INVALID，6次调用（原3次）；不是跳过样本。该脚本的进程exit 0仅说明报告生成，不是指标验收通过。

定位：新保守候选增加clause-14“争议解决”，没有付款词；原脚本在覆盖提示后把该块最后一行1299字作为结论/引文，超过现有300字限制，故被拒。说明候选扩大引入额外核对成本，并暴露脚本无法处理该分支；未改变金标，也未截短脚本答案来制造同评测绿灯。此返工尚未验收，需复审决定候选/软缺口策略并重新验证，不部署。

48d32c7测试SHA：test_chinese_clause_boundaries.py=f1271b26f479c9eb44e99cdc36a4812a1d8da2ab7854ec6cfa608c8837575017；test_chinese_clause_coverage.py=54883dcf39d5b0d488a4d8bebbc26c90e7e939a64702308bb43afc8e1bc8c431。

## 独立复审后的结构关联修订（77428b8）

Claude 对48d32c7给出Changes Requested（消息om_x100b636393ad08a0b3da10a311be713）：全文共现会错误吸收独立争议条款。接受此意见，撤回上节的全文候选策略；历史失败证据不删除。上节把独立条款命中消失概括为“真实门禁退化”过宽，结构切分前的大块词语共现本身也不证明相关。

最终策略：同块付款/例外词沿用既有规则；不同子块只在真实同父块含付款词，或本块标题路径含付款词时建立保守候选。独立相邻条款不会继承付款语境。计划和提交校验由运行时传入同一份平台切块元数据，不接受模型提供的关联。独立另一条款只写“期限延期”的隐含关系仍可能漏检，明确不声称语义覆盖。

- 新文件9 passed；五个相关文件92 passed（structural-targeted.xml、structural-related.xml）。另一次命令误写了不存在的test_dsh_findings.py，pytest exit 4、未运行测试；修正为test_dsh_payment_findings.py后得到上述92项结果，没有把误命令算作产品失败。
- 四个进程内定向突变均被捕获：去掉父块关联2 failed/6 passed；去掉标题路径关联2 failed/6 passed；不给计划传结构信息1 failed；不给提交校验传结构信息1 failed。均errors=0。后两项分别在计划candidate断言、首次提交不得提前accepted断言失败，不是导入失败。复跑脚本mutate_structural_coverage.py不写生产文件。
- 固定脚本和标签完全不变，串行重跑阿拉伯21例、中文变体21例（payment-eval-structural-*.json）：每批77次合成模型调用；正确11/11、错值拒绝10/10、字面例外5/5、无例外4/4、隐含例外0/2。long-01均恢复succeeded/3次调用，独立争议条款不再强制报告。该结果仍只证明固定控制流程，不代表真实模型准确率。
- 行首正文“第十条规定的……”可能误识别为标题，规格已明确；不扩大为自然语言标题识别。

本修订尚待独立复审；没有真实Provider、浏览器或部署验证。完整门禁仍保留既有UI超时失败，8876未变更。

## 收敛复审状态（2026-10-07）

77428b8/e18b35e已获mymacclaude代码与离线行为Approved，取代上节“尚待独立复审”的当时状态。对方分别报告30项与66项通过（范围重叠，不累加），未重跑两套SDK评测。M1编号子项静默漏报、Markdown/无标题误关联及章标题自成块已补规格并登记DSH-COVERAGE-01；详见[independent-review.md](independent-review.md)。本次仅文档/治理更新；完整门禁未通过，8876仍未变更。
