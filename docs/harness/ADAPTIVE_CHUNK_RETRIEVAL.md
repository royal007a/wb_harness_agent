# Adaptive Chunk Retrieval（本地确定性切片）

## 目标

把“Chunk 大小”从单一常数升级为可审计的入库—检索—评估闭环，同时保持当前安全边界：默认不使用 embedding、语义检索、外部网络、模型化 Query Expansion 或自动提高预算。

## 入库：父子文档与结构边界

`backend/adaptive_retrieval.py` 先按章/条/编号标题（含 Markdown、中文序号）划分父文档，再按段落、列表/表格行和句末边界形成子 Chunk；只有单个原子单元仍超限时才使用 `hard_limit`。父文档和子文档都受实际 hard limit 约束，ID 由内容和局部前缀寻址，不依赖全局序号。每个子 Chunk 带原文、offset、`parent_id`、结构路径、策略、长度和 SHA-256；`expand_parent_context` 只扩展命中的父文档，不能把整库父文档全部注入。

## 检索：动态多路与父文档提升

候选统一成 `child_id/parent_id/route/rank` 后做加权 RRF：`score = Σ weight(route)/(60 + rank)`，每路有独立 TopK，路由、权重和 TopK 写入返回策略快照。父文档只取每个父文档前三个子命中的归一化聚合分，不能被大量低排名重复命中刷高。函数内部拒绝 semantic/api、负权重和未知路由；当前实现只提供 keyword、temporal、graph 的确定性融合。

## 控制：Slot/Gap 与最小充分检索

每个最小目标声明关键 Claim/slot。每轮将 evidence 绑定到 slot，只有所有必需 slot 都有准入证据且没有 blocking gap 才能停止；迭代次数不是完成条件。连续无新增 slot 时应改写 Query 或切换已准入 route 一次，仍无进展则停止或转人工。所有轮次继续服从 retrieval-state@2 的固定预算、最大轮数和硬熔断，动态策略不能增加上限或解锁 tier 3。

## 评估闭环

`harness/adaptive_chunk_evaluation.py` 提供 2 个调参、2 个留出 fixture，对比固定窗口和自适应父子 Chunk 的 Recall@1，并真实计算父上下文完整率；留出集包含跨固定窗口边界的长条款，当前输出 fixed=0.0、adaptive=1.0、parent expansion=1.0，且 model/external calls=0。生产闭环还应在同一留出集上比较单路/加权 RRF/父聚合和首个有用结果时间、p50/p95 与成本；每次改 Chunk、TopK、路权或停止规则都跑同一集，Bad Case 必须归因到入库、召回、融合、重排或停止阶段。
