# Product HTTP 边界与契约负例（HA-0065）

基线0ee58a0，承接HA-0062独立复审。目标是让已发布的Product合同在边界值仍成立，
并使删除关键约束的回归不能靠正例校验空过。不是全系统Schema或身份认证重构。

## 合同

1. Product事件after为整数，范围0至9223372036854775807（SQLite signed int64），
   默认0。越界或非法查询422/VALIDATION_ERROR，不调用事件读取器，不产生写入，
   不变成500；最大合法值查不到事件返回空页且next_cursor原样保持。已有500条
   分页、顺序、Run隔离不变。源Schema、静态和动态OpenAPI一致公开上界。
2. next_cursor及持久Event.sequence、Run.latest_sequence也不超过上述上界。
   Store.events直接调用同样拒绝非整数、bool和越界；HTTP参数仍沿用FastAPI的
   字符串到int转换，不在本任务额外发明查询词法。整数序列耗尽的写入恢复不在范围。
3. Event.task_id / Event.run_id / Artifact.run_id使用与现有Product Task/Run一致
   的ID前缀/字符格式，拒绝其他Session/Team域ID。格式验证不证明引用存在或同域。
4. Task详情必须同时有task与runs；错误必须是完整local_http_error、retryable固定
   false。动态所有已声明422也必须引用该信封，不能靠HTTPValidationError的宽松
   object接受正例。删除required或放宽const的突变必须被新增负例抓住。
5. 服务时间测试检查器只接受实际UTC输出格式（Z或+00:00，合法日历日期）；naive、
   非UTC偏移、错误格式、非法日期拒绝。测试必须经真实Schema与FormatChecker，
   不只直接调用自写函数；通用非字符串类型交给Schema type拒绝。

## 验证与边界

用TestClient/临时SQLite创建实际Task/Run/Event/Artifact实例，再单点变异，并对
源、静态、动态三份合同做相同正反例。边界包含max-1/max/max+1、负数、大整数、
空结果与未知Run、查询异常无写入；适用的三组已知松约束另做定向突变测试。
先保存旧版失败，再冻结最终测试在旧提交重跑；定向/全量/verify及固定提交独立review。

不解决REQUEST-ID-01、通用OpenAPI字面$ref投影、其他模块空Schema，也不宣称
约束能自动检查所有持久坏数据。公开契约收紧属于刻意兼容变化；合法HTTP行为不变。
仅离线验证，不触碰8765、132、正式DB、Provider、凭据或部署拓扑；实际发布仍须
兼容本机拓扑明确后先本机再132，不能用Schema通过替代发布。
