# 核心 Product HTTP 契约（HA-0062）

基线d46f406。HA-0061证明入口可测，未证明公开文档能正确描述它们。
本轮将当前本地Product链路与公开静态/动态响应契约对齐；不借目标架构改变业务。

## 当前合同

- health是静态存活对象，不是release或Provider健康/调用计数。
- resources是本地登记元数据（CSV、synthetic JSON、Public PDF）；不返回原始字节。
  GET列表/详情、POST CSV及PDF登记的响应使用同一结构；不是目标ResourceHandle。
- POST tasks和local/tasks返回`{task,initial_run}`，没有links。
- GET tasks为`{items:[{task,latest_run}]}`，latest_run可null；GET task详情为
  `{task,runs}`，包含该Task的所有Run，不混淆这两种响应。
- POST task/runs返回新Run；reason可省略或为不超过2000字符的文本，不限定retry/rerun。
- GET run与POST cancel返回Run，取消HTTP200且不要求幂等键，终态保持不变。
- events为JSON游标`{items,next_cursor}`，after非负、默认0、每页最多500。
  不支持Last-Event-ID/SSE；不能把聊天Runtime的SSE写到此Product接口上。
- Run/Task的artifact列表返回metadata；下载按实际media_type返回原始字节，支持
  download布尔参数。sample为CSV，不能在OpenAPI声明application/json。
- 对上述入口的错误响应声明当前`{error:{code,message,retryable,request_id}}`，
  用真实422/404/403等实例校验，不把FastAPI默认HTTPValidationError当实际错误体。

## 实现约定与验证

保留已有Task/Run/Event/Artifact语义，在core bundle增加明确local_http前缀的
HTTP封装定义；静态和动态均引用同一份定义，不复制模型结构或使用空object兜底。
通用Run和资源端点可返回研究等引擎创建的数据，必须包含混合来源的实例验证，
不能只对CSV场景过拟合。Schema形状校验不替代权限、跨对象绑定和时序检查。

先用旧版运行四种文档漂移和空占位负例。修复后逐项验证创建/读取/取消/重跑/
完成/事件分页/产物下载、成功与错误状态；动态/静态/源Schema判定一致，空对象、
未知字段和嵌套损坏被拒绝。固定提交交独立review。与剩余Memory/Research/Pi/
Team响应空占位分开计数，不能称“全OpenAPI已完整”。

日期验证显式覆盖服务实际输出的UTC时间格式、无效日期和任意字符串；当前venv
的通用FormatChecker缺少可选date-time依赖，不能只传入它就算验证了时间。
本测试检查器不是任意RFC3339（例如闰秒或非UTC时区）的通用实现。

兼容性：HTTP请求响应不变，仅文档修正；基于旧错误定义生成的客户端需重新生成。
当前未实现的approval等Draft必须标注未实现，不因出现在静态文件就算可调用。
真实双端部署仍遵循本机→132，未解决本机拓扑前只报告代码验证，不宣称发布。
