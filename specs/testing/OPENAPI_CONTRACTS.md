# OpenAPI 合同归属与实例验证（HA-0058）

范围：已加载 JSON Schema 的无损注册与引用解析；Lab/Runtime 的所有现有配置、
列表、状态、详情、readiness 和消息接口。不是全系统全部业务路径验收，也不增加接口。

## 不变量

1. Lab、Runtime、研究模拟的定义分别进入 `agent_lab_`、`agent_runtime_`、
   `research_agents_` 命名空间。只转换 Schema 的 `$ref`，不修改描述或枚举文本。
   Lab 不接受 credential_ref，ID 保持 ppr/mdl/agt/chs/chm；Runtime 保持 rtp/rtm/
   rta/rts/rtx/rte；研究 Skill 不可被外部 ZIP Skill 的同名定义覆盖。
2. 所有契约注册都经过同一个冲突检查：完全相同的旧共享定义可复用；同名不同义
   在注册时失败且不部分写入。源契约不被原地修改，不允许依赖导入顺序覆盖。
3. 动态文档的所有本地引用均可解析；不使用网络加载 Schema。静态文档继续引用
   对应版本化 JSON 文件，Lab/Runtime 实例在静态、动态与源契约上判定一致。
4. 两组 POST 配置的 201、GET 列表（空与非空）、runtime、session detail、
   Runtime readiness、POST 消息事件都有具体响应 Schema，而非空对象占位。
5. Schema 描述结构；依赖启用状态、已登记实体和默认模型门禁仍由运行时代码校验，
   不能因为文档可验证就声称调用获准或真实 Provider 可用。

## 验证矩阵

- 旧版反例：Lab 正确 ID 的请求被动态 Schema 错拒；Lab credential_ref 被错放；
  动态配置响应/列表没有约束；研究 manifest 被另一域覆盖。
- 实例回归：两域创建 Provider→Model→Agent→Session，验证请求与 201；空/非空
  列表、运行状态、session detail、readiness；未知字段、跨域 ID 与错误前缀拒绝。
- SSE：Lab 明示 local_demo；Runtime 默认 MODEL_RUNTIME_DISABLED；每帧按本域
  Schema 验证，持久状态与幂等重放一致，不调用 Provider/Keychain/外网。
- 注册器：不同来源同名不同义原子拒绝、相同定义可复用、前缀内部引用不串域、
  原文描述不被替换、源定义不变、悬空引用可被门禁发现。
- 完整 verify + Workbench；代码 review 与真实双端部署分别记录，部署阻塞不隐去。

命令：`pytest -q tests/test_openapi_contracts.py tests/test_agent_lab.py tests/test_agent_runtime.py tests/test_workbench.py`。

兼容性：只修文档的 component ID 与补缺失响应，不改变请求 JSON、持久 ID、
业务响应或状态机。依赖旧错误 component 名的 SDK 需重新生成；不保留有歧义的别名。

独立review已知Low：第1条对字面数据的保证尚不完整。递归投影会改写嵌在
const/enum/default/examples中的同形$ref；当前已加载spec没有此实例，后续仍需
跳过这些数据关键字并补回归。Runtime status固定0计数字段是静态声明而非用量
遥测；本规格通过不证明真实模型请求次数为0。
