# Team 幂等回放的当前资格（HA-0064）

基线116a164。TEAM-REPLAY-01：Session创建成功后Channel归档，detail和新key拒绝，
旧key却回放成功。相同封装存在Foundation/Task/Attention/Session及Recovery。

## 合同

1. 25个写入口的缓存命中必须在同一SQLite事务中，先核对请求digest，再执行必填的
   只读回放授权，最后才能返回原响应。不同body仍409/CONFLICT且不返回缓存；不存在
   缓存才执行原动作。key/输入/敏感元数据验证保持原样。
2. 回放授权重查当前identity、Workspace/Channel状态、membership、clearance及对应
   操作role。Session须仍是同一owner；Attention操作须仍是同一target；Recovery须
   是同一case owner；Gate须仍是该Task指定reviewer。直接授权路径读取的当前主体、
   目标或引用缺失拒绝，
   DB/授权服务故障不转成缓存成功。损坏Foundation记录继承HA-0063的500语义。
3. 缓存只是历史操作收据，不是重新执行资格、当前状态或当前租约。授权通过后逐字
   返回原JSON，不改写缓存；不重新运行CAS、lease、状态转换、freshness、预算消耗、
   snapshot、过期回收或动作，因此完成/取消/retired后的合法重放仍可成功。
4. 所有授权检查必须只读，不先执行动作再回滚；成功/失败回放均不新增DB写入，
   不刷新lease、计数、cursor、Handoff、Gate、Case或幂等记录。允许重新获准后再次
   读取原收据；被拒期间不删除证据。新key继续完整执行原业务校验。

## 逐入口授权映射

| 写入口 | 回放当前资格 |
|---|---|
| Foundation创建Workspace | 仍是local_admin，目标Workspace的当前admin资格 |
| 创建Agent、授予Workspace membership | 当前目标Workspace admin；对应目标存在 |
| 创建Channel | 当前Workspace admin，创建的Channel仍可访问 |
| 授予Channel membership | 当前Channel存在且active，其Workspace admin（不新增Channel role要求） |
| Task创建/claim/handoff/submit/close/Gate（6） | 当前Task scope，分别coordinator / contributor或coordinator / 同前 / 同前 / contributor或coordinator或reviewer / reviewer或coordinator；Gate再绑定reviewer |
| Attention创建/read/claim/release/complete（5） | 创建者当前Channel资格；read的当前Channel；后三者当前item target+scope |
| Session创建/handoff（2） | 当前Session owner+scope，状态/版本推进不阻止历史回放 |
| Recovery创建/observe/try/confirm/cancel/link/complete（7） | 当前case owner、对应Task scope、contributor或coordinator，不需要仍持有执行lease |

读取当前对象同时核对其与缓存中已保存的scope/owner关联不漂移，发现变化拒绝
409/TEAM_REPLAY_SCOPE_CHANGED。旧收据没有保存的上游关系不能事后推导：例如
Channel grant只含channel_id，Recovery只含team_task_id，不保存当时全部上游scope。
它们重查当前上游授权，但不能由此宣称能发现任意历史上游重绑；当前没有重绑API。
该检查不是缓存全文完整性/签名审计，也不扫描所有嵌套引用或其他模块的幂等实现。

## 验收

通过真实HTTP建立全部25类收据。先在旧版运行至少每入口1个权限变化反例，再覆盖：
主体暂停、Workspace撤销/归档/clearance、Channel撤销/归档、role降级、owner/target
变化、目标删除/错域、损坏及授权故障；断言明确错误和不泄露缓存。合法重放应与原响应
相同，DB total_changes=0，合法终态/过期后也不重执行业务；冲突body与新key语义不变。
HTTP测试使用临时SQLite，Runtime凭据/Adapter为哨兵；至少一次重启后重验资格。
冻结最终测试并在旧提交重跑，相关测试、全量、verify与独立review都需证据。

不新增认证/在线撤销API、不启用模型/工具、不操作正式数据。25入口不是全系统
幂等机制验收。部署仍需兼容本机拓扑决定后先本机再132。
