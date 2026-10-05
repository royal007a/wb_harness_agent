# HA-0076：Adapter 内容与持久观察事件分流

范围：ADR-0076、metadata Schema/投影、Native/Pi 持久入口、Pi stderr、回归与部署证据。作为 A 包第一切片，不代表整个 A/B/C 实施完成。

1. 先写契约，原始结果留内存；持久入口白名单投影。
2. 合成秘密覆盖文本、工具、errors、structured_output、stderr、未知字段和 kind；合法 Native 聚合/Pi 候选不退化。
3. 验证未知 kind/非法 JSON 失败且不持久原文；Schema 拒绝未知字段；旧行保留且重启读取一致。
4. 定向、工作台、全量 verify；固定提交发独立 review。
5. 两端发布前检查版本/备份/拓扑；先8765再132，记录真实发布结果或阻塞，不以测试代替部署。

停止条件：需要变更 CLI 认证/准入或本机 launchd 域时请求用户，不默许放权。DB/Provider 和 shared CLI 目录不用于回归测试。
