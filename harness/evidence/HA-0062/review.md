# HA-0062 独立复审记录

2026-10-04，mymacclaude对固定7ac1498给出Approved。以下是独立review回报，
不是本轮主代理再次执行的测试。只读worktree/临时SQLite，无真实服务或部署。

- 新测试52项、相关四文件190项通过；17入口静态/动态状态、媒体、请求/错误声明一致。
- 实际CSV及两类研究生命周期、PDF登记、Pi失败路径生成的实例通过两套Schema。
- 2431条测试DB记录通过源Schema；1001事件分页500/500/1/0，连续且末页cursor保持。
- UTC检查插桩3672次、654个实际时间戳；服务输出naive/+08:00的突变被杀死。
- 21个突变杀死17个，不能称所有声明均有回归保护。

## Low及后续

1. before.xml用早期19项测试生成，未保存该版测试源码。当前文件放回基线时创建/
   详情会先在`$ref`helper报KeyError；其余17项原因一致。acceptance已纠正；
   原业务漂移独立证实，不能据此声称当前测试可原样复现全部历史行为失败。
2. 缺三条保护：删除动态422信封绑定、task_detail.required缺runs、retryable放宽
   为boolean，现测试仍通过。应补精确反例与突变验证，不靠正例校验空松Schema。
3. UTC检查器自身缺naive/非UTC负例；输出端有保护不代表检查器自身不易被改坏。
4. 既有契约/边界：after>=2^63合法声明值触发500；Event run_id/task_id和Artifact
   run_id缺格式约束（不是引用存在性检查）；错误body request_id和响应头可能不一致，
   middleware拒绝路径无该头。需后续分别明确合同、测试与修复。

Pi成功/waiting_approval、研究重跑执行引擎、真实ASGI/浏览器/Provider/双部署未验。
review期间的HA-0063未提交改动由mymaccodex产生，reviewer未修改主仓库。
