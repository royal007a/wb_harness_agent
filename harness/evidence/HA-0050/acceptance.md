# HA-0050 Acceptance Evidence

- 状态：completed; independent review Approved（HEAD a694de3）
- `tests/test_adaptive_retrieval.py`: 5 passed
- `adaptive-chunk@1` Schema 校验父子 ID、哈希、结构路径和策略枚举。
- weighted RRF 在函数内部拒绝未准入路由，限制每路 TopK，并记录权重快照；Slot/Gap 控制器在预算耗尽时硬停，并支持一次无进展策略切换。
- 长章节回归验证父块与子块均逐字对齐 `source[start:end]`，并验证子区间覆盖原文全部非空白字符。
- `harness/adaptive_chunk_evaluation.py` 使用 2 个调参、2 个留出 fixture，真实输出留出 Recall@1 fixed=0.0、adaptive=1.0、父上下文完整率=1.0、model_calls=0、external_calls=0；这只是本地合成评测，不是线上 Agentic RAG 证据。
