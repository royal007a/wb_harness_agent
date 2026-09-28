# HA-0050 Adaptive Chunk Retrieval

## 目标

交付结构感知父子 Chunk、确定性动态多路融合、Slot/Gap 最小充分停止的本地切片，并建立可回归的入库—检索—评估口径。

## 范围

- `backend/adaptive_retrieval.py` 及其单元测试、`adaptive-chunk@1` Schema。
- 文档与 ADR；verify 纳入 fixture。

## 非目标

embedding、semantic/api、外部网络、真实 Provider、自动扩大预算、生产 reranker 或缓存。

## 验收

- 父子 lineage、结构边界、硬上限和哈希可机器校验。
- weighted RRF、slot progress、blocking gap 行为有确定性测试。
- 全量 Harness verify 通过；证据如实标注为本地切片。
