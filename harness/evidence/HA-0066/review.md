# HA-0066 独立复审

2026-10-04，mymacclaude 对固定 5429c62 给出 Approved，2 Low、1 Info。
引用交接 om_x100b632c71db0ca4c471345fe4122bb；复审消息
om_x100b632c14b2b4a0dee1a90408e0602。以下为 reviewer 回报，不冒充作者重跑。

- 指定四文件 108 passed；最终测试回 e6e1fb9 是 36 failures、0 errors。
  其中 35 次 empty payload accepted 和 1 次绑定断言，不是 36 个独立漏洞。
- 真实 Bank retain/retract/delete、三种研究根/Child/取消/重跑/重启实例与
  源/静态/动态合同一致；计数是存量，撤回不减少、删除才减少。
- FTS 三种构造状态与八类准入档案共 24 组投影通过，semantic runtime 始终
  关闭；读取无 DB 变化，凭据/Adapter/执行/外连哨兵未触发。八项突变均被杀死。
- 默认 jsonschema 不自动检查 date-time；使用仓库 FORMATS 后非法日期被拒。

## 后续，不阻塞本次批准

1. 缺三种负例：counts.sources 的 minimum、semantic external_calls 的 minimum、
   keyword 不可用时 error 必须是 string。生产 Schema 正确，删除约束突变存活。
2. 既有 Memory 非 UTF-8 准入文件会 500（UnicodeDecodeError 未捕获）；需独立
   修复，不把本轮公开错误信封校验等同已经恢复关闭状态。
3. 静态文档仍缺 POST /local/research 与 GET /local/research/{runId}，不在本项。

边界：临时 SQLite/TestClient，不是真实 socket 或部署；native 未执行，FTS
故障为磁盘构造而非真正无 FTS 的构建。更多档案异常/启动数据库故障未经完整验证。
复审的读取范围与本项 6 GET + 1 POST 的公开合同范围不可直接按数量等同。
