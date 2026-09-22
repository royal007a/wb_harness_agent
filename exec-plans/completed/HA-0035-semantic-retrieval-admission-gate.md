# HA-0035：实现 M2-B Semantic Retrieval Admission Gate

## Objective

为后续 M2-B embedding/vector、RRF/rerank 建立版本化、机器可验证、默认关闭的准入 Gate，避免尚未审核的 Provider、语料或网络出口被误启用。

## Scope

1. 定义 ADR-0031、机器 Schema、初始 `not_admitted` 状态和校验器。
2. 将 Gate 的状态与阻塞条件暴露在本机 Memory Runtime；不读取任何秘密或第三方资料。
3. 覆盖 Schema 无效、not-admitted 零调用、伪 admitted 证据缺失、Runtime 一致性和重启反例。
4. 按双环境规则发布默认关闭的 Gate，记录可恢复备份、健康、Runtime、认证边界与 Evidence。

## Non-goals

- 下载/运行 embedding 模型、调用 Provider/网络、建立 vector index、RRF/rerank、自动语义召回或改变 M1/M2/M3 现有返回。
- 把 Gate 变成数据外发/隐私/性能证明，或绕过用户审批。

## Acceptance

- 无完整版本化 Evidence 时，Gate 必为 not_admitted/disabled/zero calls；Runtime 与状态一致。
- 任意试图用缺失或不完整 admission evidence 声称 enabled 的输入被机器校验拒绝。
- 回归、Gate 评测、本机和公网默认关闭发布及认证边界验证通过。
