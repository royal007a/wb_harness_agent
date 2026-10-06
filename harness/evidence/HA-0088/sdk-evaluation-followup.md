# 固定脚本评测实际SDK重跑

2026-10-07，本机冻结a5ec114（生产运行代码4b8ec1e），串行运行：

```sh
env -u ARK_API_KEY -u HARNESS_DSH_REAL_ENABLED -u HARNESS_DSH_CREDENTIAL_REF \
TMPDIR=/private/tmp .venv/bin/python harness/dsh_payment_eval.py --out /tmp/ha88-eval.json
```

退出码0。报告原样保存为sdk-eval-v2.json，stdout为sdk-eval-v2.log；报告只有指标、样本ID和状态，没有正文、凭证或生产数据。

这次实际执行官方DSH SDK、平台网关和临时SQLite，使用现有label-blind脚本Provider；不是先前评分器测试构造的理想record，也不是真实豆包。21个case都执行后才加载labels。10个故意错值case以DSH_FINDINGS_INVALID失败且未发布，另外11个成功。

| 指标 | 命中 / 分母 |
|---|---:|
| 错值不发布 | 10 / 10 |
| 正确值发布 | 11 / 11 |
| 字面例外呈现 | 5 / 5 |
| 无例外候选误报检查 | 4 / 4 |
| 隐含例外被平台词表识别 | 0 / 2 |

最后一项保留失败，不因模型有时能理解隐含例外就更改金标或词表指标。分母是固定合成输入，不是业务准确率；数据集未扩大，不能宣称模型质量改善。

SDK评测完成后才启动第五轮完整verify.sh，不与自己的浏览器或其他SDK测试并行。完整门禁和独立复审仍是另外的发布前提。
