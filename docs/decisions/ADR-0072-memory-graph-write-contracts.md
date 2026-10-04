# ADR-0072：图写入回执契约和支撑来源的时间一致性

状态：Accepted for implementation；2026-10-04。基线a78d535。

HA70复审发现Entity/Relation动态OpenAPI缺默认错误信封，静态仍引用旧Error。
成功Schema原已存在，但未绑定去重和audit_id分支；现有幂等header已有128上限，
本轮补边界回归而不称新增限制。
同时图读取排除未来Source，图写入只检查Fact时间与Source到期，可能接受尚未
发生的Source作为当前有效证据。

决策：两个POST复用local_http_error和1..128幂等header；保留201，不改变对象ID。
deduplicated=true时audit_id必须null，false时必须是memaudit引用。新写入/新key
去重都要求同Bank、active且时间有效的支撑Fact及Source；Source.occurred_at不能
晚于当前时刻。Relation两端Entity的支撑也经过同一检查。

同key仍按HA70回放历史收据，不重新授权执行或按当前时间重新生成；supersede/
retract尚未物理删除canonical时可保留历史active视图。删除关联canonical后旧key
409且不复活。没有新增自动实体提取、Provider、身份体系、图推理或缓存。

用临时DB的三套Schema正负例、事务注入、重启和旧版行为反例验收；不声称
图质量、引用存在性被JSON Schema完全证明、全接口完成或双端已经部署。
