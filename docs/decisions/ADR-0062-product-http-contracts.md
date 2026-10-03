# ADR-0062：公开合同必须描述实际Product链路

状态：代码验证完成，独立review与双部署待完成；HA-0062，基线d46f406。

HA-0061之后审查发现四种明确漂移：CreateTaskResponse要求未返回的links，
TaskView把详情的runs写成latest_run，cancel声明202但实际200，events声明SSE
但实际JSON游标。动态文档对应成功响应多数是空Schema，不能检出这些漂移。

决定：已有业务行为不变；core bundle新增local_http命名的响应封装及本地资源
元数据定义，静态与动态共用。实际Product入口优先于历史目标接口描述；目标审批
等尚未实现操作显式标记。补实际HTTP实例、负例和静态/动态同集校验。

本轮不启用模型、不拓展执行权限、不建设鉴权或全局Response拦截器；错误仍由
现有middleware处理。其余模块契约和helper字面$ref的Low另行处理。
规格见specs/testing/PRODUCT_HTTP_CONTRACTS.md，运行验收仍须独立双部署证据。

验证：旧19项行为反例失败，新52项通过，相关190通过，全量684 passed/16 skipped，
完整verify exit0。具体证据及不证明什么见harness/evidence/HA-0062/acceptance.md。
