# HA-0069 Memory写入HTTP与失败边界

基线697ef73；候选工作树。未部署，未获得本项独立Approved。

## 实现

- Retain/撤回/删除成功响应从空声明改为三套同源合同；当前错误信封及撤回请求体
  同步绑定。没有新增端点或执行权限。
- semantic档案显式UTF-8读取；ValueError（含UnicodeDecodeError/JSONDecodeError）
  与RecursionError降级invalid_not_admitted，只公开类型，runtime始终false。
  RuntimeError等意外程序故障仍传播，不泛化为吞掉一切故障。
- DELETE已有Content-Length检查保留，再检查实际ASGI流；第一个非空chunk即422，
  不缓冲后续正文，不执行业务。真实网络协议/反向代理行为未在本项验证。
- 没改M1事务/历史幂等语义；三套Schema描述实际首次/去重/重复撤回分支，
  不把旧收据当当前状态。清除canonical并不等于清理所有历史派生正文。

## 证据

新测试tests/test_memory_write_contracts.py（40项），SHA-256：
`6fa0a3ffe3991fcef651c6621b58f029a37c4b30930aa6aa06ac86df40511909`。

|文件|结果|范围|
|---|---|---|
|before-initial.xml|1 collection error|误用pytest入口未带项目路径；不是反例证据|
|before-behavior.xml|5 failed/1 passed|早期6项：4个业务失败，deep样本错误地要求特定异常类型，已修测试|
|before-final.xml/log|35 failed/5 passed/errors=0，5.15s|最终40测试原样回697ef73；保留基线helper/业务/Schema|
|new-initial.xml|36 passed|增加并发/重启/ASGI/异常注入前|
|new.xml|40 passed，5.26s|最终定向测试|
|targeted.xml/log|192 passed，27.25s|13文件：Memory所有现有路径、admission、OpenAPI、Workbench|
|full.log|1265 passed/16 skipped，180.59s|全量；跳过项不算通过|
|mutation-*.xml/log|10/10被杀死，errors=0|独立临时worktree；逐次反向patch还原并cmp|

before-final的35失败不是35个独立bug，多数来自同一空公开声明。
deep数组在当前Python可成功解析然后被Schema拒绝；额外注入RecursionError锁住
解析器递归失败分支，不声称该具体数组在当前版本一定触发递归异常。

mutation-draft-admission/body两份记录为试验脚手架误删缩进导致collection error，
修正生成patch并还原后重跑，不计入10个有效突变。详见mutation-plan/results.json。
初版late-audit突变在seed阶段就失败，保留为mutation-draft-late-audit，不作事务
保护证据。最终late-audit-commit改为DELETE canonical之后提前提交，seed正常，
失败落在持久表快照差异断言；重新还原cmp并清理第三个临时worktree。
10/10仅指列出的定向突变，不是完整mutation score。

targeted观察74个入口，其中72个有passing-test 2xx；full观察148个，均有
passing-test 2xx。144份源码/合同/测试/功能映射哈希稳定，运行后比对无漂移。
观察器标记697ef73+dirty候选，不把执行归属伪造为之后固定提交。
已完成输出仅机械清理行尾空白，参数化XML testcase名改摘要，观察JSON压为单行；
不改结果/源哈希。两个临时测试worktree已清理，正式运行配置和数据未变。

## not_evidence / 已知未完成

- 只用临时SQLite/TestClient、合成Source/Fact、两个本进程线程及直接ASGI endpoint
  调用。重启为同进程关闭app后重开同DB，不是机器重启或多进程线性化证明。
- 故障后比对所有持久表快照；SQLite total_changes包含已回滚尝试，不能要求它
  在故障时不变。成功回放则额外断言total_changes不变。
- 没碰8765、132、正式DB、Provider、Keychain、launchctl。先本机后132发布仍待
  HA-0056兼容拓扑前提，不以离线测试取代双端发布。
- **MEMORY-DELETE-01**：删除后旧Retain收据仍可回放Fact statement；Entity等历史
  收据也需统一失效。已登记，不称全库删除/隐私抹除。WAL/备份擦除同样未验证。
- **MEMORY-FTS-01**：FTS不可用时Retain仍依赖索引写入，可能500；事务不半写，
  但没有实现M1写入降级。本轮没有改动该边界。
- 档案读取没有新增文件字节上限，JSON容错不等于抗超大本机文件DoS。
- 仍有22个API加1个页面的成功JSON声明恰为空；缺content/宽松非空声明另计，
  见remaining-empty-responses.json。全接口/功能和真实部署目标均未完成。

## 收口

`bash harness/verify.sh`退出0；全量1265 passed/16 skipped，检索/Agentic/adaptive
及确定性Memory/Team评测、两类准入检查、JS语法、inventory/diff检查通过。
见verify.log；最终144份源码哈希无漂移。固定提交送mymacclaude只读复审，
Work Item保持blocked（review及双部署未验收），12小时整体目标仍在推进。
