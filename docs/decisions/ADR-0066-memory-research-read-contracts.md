# ADR-0066：公开Memory与Research读取的实际响应

状态：实现与离线验证完成，待固定提交独立复审及双部署；基线e6e1fb9，HA-0066。

行为测试已有Bank/Research历史读取覆盖，但公开成功响应仍为空。决定复用现有
memory_bank与Product Run，在各自源Schema增加明确local_http命名的封装；
Research列表以allOf表达本引擎根Run限制，不复制Run定义。不改变执行门禁。

Memory运行状态不是固定样例：FTS失败和semantic档案异常也应有合法合同；即使
档案admitted也不启用runtime。Schema描述可返回的形状，不是授权证据。错误复用
当前HTTP信封。相关源、静态与动态合同由实际HTTP实例、负例及突变共同验收。

规格：specs/testing/MEMORY_RESEARCH_READ_CONTRACTS.md。真实双部署单独验收。
