# ADR-0031：以机器 Admission Gate 阻止未批准的 M2-B 语义检索

状态：Proposed（本地受限实现，HA-0035 已完成双环境验收）
日期：2026-09-20

## 背景

M2-A 仅使用本机 FTS5 keyword index；M3-A/M3-B 分别提供显式关系路径和 exact Entity Catalog。它们都不是 embedding/vector、RRF/rerank 或语义检索。将 embedding 模型、语料、网络出口或真实业务资料接入前，必须先确认处理边界、删除传播、评测与成本，不能只依靠环境变量或口头说明。

## 决策

增加版本化 `memory-semantic-admission@1` 状态和 Schema：

1. 默认 `not_admitted`、`enabled=false`、模型/外部调用均为 0，并给出阻塞条件。
2. 只有在版本化语料 manifest、数据外发审查、删除/重建演练、离线相关性评测和延迟/成本基线均有 Evidence 时，状态才可以变为 `admitted`。
3. 当前运行时只公开该 Gate 状态；不安装/下载模型、不配置 Provider、不创建 embedding 索引，也不向 Model/Adapter 注入记忆。
4. Gate 通过不等于上线：接入实现仍须新 Work Item、权限、预算、真实 L3 与回滚验证。

## 后果

该 Gate 防止“有一个向量库配置”被误报为已获批的语义记忆。它本身不能验证第三方审查真实性或替代真正的模型/性能/删除测试。
