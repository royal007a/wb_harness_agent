# Memory / Research 读取响应合同（HA-0066）

基线e6e1fb9。承接READ-SCHEMA-01；测试请求命中不能替代公开机器契约。

## 范围与不变量

- Memory runtime为当前M3-B能力状态；Bank列表返回items及runtime，详情返回
  bank、counts及runtime，Bank创建仍返回单个memory_bank。counts是已存Source/
  Fact数量，不是active或当前可召回数。沿用固定local_admin/ws_local身份边界。
- runtime显式描述FTS可用和不可用两种情况，以及semantic准入档案的not_admitted、
  admitted、invalid_not_admitted三种投影。admitted是档案状态，不是运行许可；
  runtime_enabled仍恒false，model_calls/external_calls是档案内记录，不是遥测。
  不把开发机FTS正常或当前默认档案硬编码成唯一合法响应。
- 三种Research列表返回items中的本引擎根Product Run，不返回Child或其他引擎；
  复用core Run，以allOf约束selected_engine及缺省或null的parent_run_id。读取已保存
  历史不依赖执行门禁开启；GET无模型/工具/凭据调用或数据库写入。
- 四个读取入口加Memory runtime/详情/创建共7项，源、静态、动态成功响应一致；
  错误使用当前local_http_error信封，不沿用未来Error草图或宽松HTTPValidationError。
  空对象、缺字段、多字段、嵌套坏数据、错误引擎和Child必须被契约拒绝。
- 静态文档补已存在的GET /local/research和GET /local/memory/banks/{bankId}，
  不把此更改说成新增HTTP路由。路径参数保持现有字符串语义，未知Bank为404。

## 验证

真实TestClient+临时SQLite生成Bank/Source/Fact与研究父子Run，覆盖空/非空、
完成/取消/重跑/重启、门禁关闭后的Native历史。Native仅用临时准入生成元数据，
不得调用SDK、CLI、Provider或解析凭据；哨兵校验。FTS不可用与错误档案另注入故障。
先以旧版文档和真实实例证明空Schema缺陷，再对最终测试复跑基线；关键约束做
定向突变，记录失败是否是行为断言，不能把缺helper/导入错误算反例。

边界：不新增运行时响应拦截器，不修损坏DB，不新增Memory认证或多租户；不覆盖
三类研究的全部POST/详情契约或其他模块空Schema。响应声明收紧要求客户端重新
生成；合法请求/业务输出不变。真实部署仍受HA-0056本机拓扑约束，先本机再132。
