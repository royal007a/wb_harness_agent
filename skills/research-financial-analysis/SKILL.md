---
name: research-financial-analysis
version: 1.0.0
mode: first_party_local_instruction_only
---

# 财务专项（模拟）

只读取本 Child Run 分配的 synthetic 财务快照，计算净利率和资产负债率，并将每项结果绑定来源资源摘要。不得读取宿主路径、联网、加载第三方依赖或给出投资建议；缺少口径时必须返回失败。
