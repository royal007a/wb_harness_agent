# HA-0074 决策记录

用户已确认业务 Runtime 用途、每次 2000 万 Token 和套餐允许该用途。精确模型与 Base URL 见 ADR-0074；无秘密写入。

只读核对了 Faux sidecar、Pi Product Run、Pi 准入与 Claude 原生投研规格；这些入口并不会继承普通聊天 Provider 配置。

验证：任务注册表使用 Draft 2020-12 + FormatChecker 校验；检查任务 ID 唯一及文件引用存在；`git diff --check`。本记录只证明决策落档，不证明模型连通、预算硬熔断、业务输出质量或本机/132 部署。

实际调用：本任务未调用 Provider，未读取/保存 API key，未打开任何运行时门禁。没有重跑业务测试，因为生产源码未变。
