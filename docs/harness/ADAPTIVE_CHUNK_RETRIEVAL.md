# Adaptive Chunk Retrieval（本地确定性切片）

## 目标

把“Chunk 大小”从单一常数升级为可审计的入库—检索—评估闭环，同时保持当前安全边界：默认不使用 embedding、语义检索、外部网络、模型化 Query Expansion 或自动提高预算。

## 入库：父子文档与结构边界

`backend/adaptive_retrieval.py` 先按章/条/编号标题划分父文档，再按段落和句末边界形成子 Chunk；只有单个原子单元仍超限时才使用 `hard_limit`。父文档保留章节上下文，子文档是召回和证据引用的最小单元。每个子 Chunk 必须带 `parent_id`、结构路径、策略、长度和 SHA-256；召回后先以子 Chunk 排序，再按命中的子 Chunk 扩展父上下文，不能把整库父文档全部注入。

## 检索：动态多路与父文档提升

候选统一成 `child_id/parent_id/route/rank` 后做加权 RRF：`score = Σ weight(route)/(60 + rank)`，权重和各路候选数由任务的已知槽位与检索方式决定。父文档只能从真实命中的子 Chunk 获得提升，不能凭空获得分数。当前实现只提供 keyword、temporal、graph 的确定性融合；semantic/api 仍需 Admission Gate，不能由状态对象自行宣称准入。

## 控制：Slot/Gap 与最小充分检索

每个最小目标声明关键 Claim/slot。每轮将 evidence 绑定到 slot，只有所有必需 slot 都有准入证据且没有 blocking gap 才能停止；迭代次数不是完成条件。连续无新增 slot 时应改写 Query 或切换已准入 route 一次，仍无进展则停止或转人工。所有轮次继续服从 retrieval-state@2 的固定预算、最大轮数和硬熔断，动态策略不能增加上限或解锁 tier 3。

## 评估闭环

固定 fixture 同时比较固定长度、结构 Chunk、父子 Chunk、动态加权融合和迭代停止：Recall@K、slot/evidence coverage、父上下文完整率、重复率、首个有用结果时间、p50/p95 延迟和成本。每次改 Chunk、TopK、路权或停止规则都跑同一集；Bad Case 必须归因到入库、召回、融合、重排或停止阶段。结果不足时记录 evidence，不把离线通过写成真实 Agentic RAG 已启用。
