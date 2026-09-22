# HA-0036：实现 Fact Lineage Evidence

以已知 Fact ID 回溯至多八层同 Bank supersede 历史；仅返回可追溯、`as_of` 可见、Source active 的 Fact，标记 active 为当前适用、superseded 为历史。覆盖 Bank、time、retract/delete、深度/环路、重启和无 Source 正文，双环境发布。
