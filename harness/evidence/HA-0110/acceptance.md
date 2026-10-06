# HA-0110（候选，待审）：search_document 忽略空白、大小写、全半角差异

依据：jikesummary《容错艺术：多级模糊匹配》（先统计 not found 里有多少只是格式差异；匹配分级降级、保持唯一性底线）；工具摘要中“search 只做 casefold”的缺口。

修复：查询与证据块都按 `search_key` = NFKC + 去全部空白 + casefold 比较，证据块的键在 Run 开始时算一次；返回给模型的仍是原文（逐字引文校验不变）。规范化后为空的查询（全空白，原先 `'' in text` 会匹配全部块）改为 DSH_TOOL_INPUT。提示词同步说明。

验证（定向）：tests/test_dsh_search_normalization.py 8 passed（全角数字、词内空格、大小写、全角字母均命中；全空白查询被拒；返回文本为原文）。基线 5 failed；去掉空查询守卫 1 failed。付款/对抗/运行时/HA-0079 探针/评分共 185 passed。21 个评测案例在 7 个常用查询上命中集合与旧实现完全一致（diff=0），预计不改变评测指标。

边界：不是同义词扩展或模糊相似度；仍然是确定性字面匹配。
