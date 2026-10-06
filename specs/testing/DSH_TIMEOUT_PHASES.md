# DSH超时测试必须到达被验证阶段（HA-0089）

1. 本项只修改测试，不改变SDK启动、Provider期限、预算、取消或业务Run的生产配置。
2. 发送后超时用例先由真实官方SDK到达平台合成Provider，确认首次调用实际发生，再让测试专属时钟越过Run期限；不得在5秒任务尚未完成初始化时宣称已测Provider超时。
3. 分别验证Run单调时钟截止、Service持久Run年龄截止、Provider响应超时。前两者TIMEOUT，第三者DSH_PROVIDER_TIMEOUT。时钟替身只替换对应模块引用，不修改Python全局time/datetime或其他进程。
4. 每次恰好一次合成调用；发送后没有usage时spent为0、reservation冻结且status=usage_unknown；无产物、自有run目录清理、Provider协程取消，不自动重试。
5. 耗时上界从进入Provider起测量，SDK初始化另由HA-0086有界启动测试覆盖；未进入Provider仍明确失败，不跳过、不放宽成零调用可通过。
6. UI原样重跑通过仅记录事实。首次page.goto/load超时原因未证实时不宣称已修、不修改前端生产行为。最终仍须完整门禁，不能用本切片定向通过替代。
