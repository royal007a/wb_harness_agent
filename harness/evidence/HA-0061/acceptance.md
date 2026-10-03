# HA-0061：剩余读取入口行为验证

2026-10-04（北京时间）；基线fff8d75。仅测试、规格及复审记录，无业务代码改动。
状态：定向、全量观察器及完整verify通过；d46f406 已获 mymacclaude 独立 Approved。

## 范围与结果

上一轮137/148入口有观测，本轮补剩余11项。新增57个参数化测试项：
test_read_surfaces.py的55项，加Workbench的Replan列表生命周期、原生研究列表各1项。
不是新增57个产品功能；重复请求也不能替代业务断言。

| 证据 | 实测 | 说明 |
|---|---|---|
| targeted.xml / targeted-http-observations.json | 123 passed，6.81s | 三个相关文件；48入口observed，46有passing-test 2xx |
| full-http-observations.json | 632 passed / 16 skipped，57.10s，exit0 | 148/148 observed，148有passing-test 2xx；不是分支覆盖或业务验收 |
| verify.log | exit0；632 passed / 16 skipped，57.41s | 完整verify，含离线评测、前端语法及diff检查 |

运行命令：

```sh
env -u ARK_API_KEY .venv/bin/python -m pytest -q tests/test_read_surfaces.py tests/test_workbench.py tests/test_claude_research_runtime.py -p harness.pytest_interface_evidence --interface-evidence=harness/evidence/HA-0061/targeted-http-observations.json --junitxml=harness/evidence/HA-0061/targeted.xml --tb=short
env -u ARK_API_KEY .venv/bin/python -m pytest -q -p harness.pytest_interface_evidence --interface-evidence=harness/evidence/HA-0061/full-http-observations.json --tb=short
env -u ARK_API_KEY bash harness/verify.sh
```

两份观察器均记录fff8d75+working_tree_dirty，136项源码/契约/映射哈希前后一致，
并在生成后核对无变化。它们绑定本轮候选测试，不意味着基线提交自身已有这些测试。
本轮没有发现生产实现需修改的行为反例，因此不构造“旧版失败”证据。
首次新测试错误地把根Run的可选parent_run_id当成必填字段，两条KeyError已按
原契约修正为缺失或null；此为测试编写错误，不算产品修复或被隐藏的业务失败。

targeted.xml的参数化testcase名称做机械脱敏：首个`[`之前的函数名保留，其后
XML属性原样编码的后缀（包含闭括号）计算SHA-256，替换为case_sha256。原先
test_bad_csv_rejected名称包含2MiB合成输入；仅压缩名称，不改123条结论、计数或耗时。

## 实际断言

- Resource：CSV/PDF登记的哈希、大小、分类、编码、行列与上传响应一致；同内容
  改名不重复，倒序、详情、404、无正文、实际重启后的持久数据一致。
- Memory Bank：空/非空、固定local所有权、幂等与倒序；详情计数一致、无Source/
  Fact正文，实际重启仍在。Bank项用源Schema和额外字段负例验证，不冒充列表已有
  公开响应Schema。runtime字段与独立runtime读取一致。
- 两个确定性研究引擎：只列本引擎根Run，排除Child/其他引擎；幂等、取消和完成
  状态与详情一致。原生研究仅在临时测试准入下创建元数据，不执行，取消后关闭
  门禁、重启仍可读取历史；新增POST继续409。哨兵禁止native stream和Runtime
  凭据/Adapter调用。合成PDF只证明登记，不证明解析真实PDF。
- Replan：源Run隔离、空列表/不存在404，proposed→awaiting_confirmation→
  cancelled→重新提案→confirmed；读操作不写DB或执行恢复，新Run只由Confirm
  生成且仍queued。使用已发布ReplanList Schema及额外字段负例。
- sample逐字匹配版本化CSV，下载头正确，读取不自动登记资源；health明确只验证
  静态进程响应，不能当作Provider/PID/release就绪证据。
- OpenAPI/静态HEAD的状态、类型、长度等与GET一致，客户端收到空正文；该断言
  证明传输层行为，不证明应用ASGI没有发出body。静态缺失/越界404。
  11入口分别覆盖Host、Origin、Sec-Fetch-Site拒绝和错误代理前缀，无DB变更。

## 边界与未完成

- 全部用TestClient和临时SQLite，不是公网或真实socket验收；没有修改正式DB、
  8765、132、Keychain或实际准入档案，没有执行CLI/容器/Provider。
- health/resources、Bank列表、三类research列表公开成功响应Schema仍为空或缺失；
  字段断言不替代机器契约。详见READ_SURFACES.md和GAPS.md中的READ-SCHEMA-01。
- 148入口均观察到不证明全部分支、错误路径、断言充分性或真实功能可用；16 skipped
  不算通过。部署、浏览器/容器/真实模型及参考架构声明对照仍是总目标的待办。
- 本轮仅补测试和规格，无需切换服务；此前代码修复双部署仍因本机拓扑决定阻塞，
  不能把代码Approved说成已经上线。仍遵守本机先于132，不私自换launchd域。
- HA-0058、HA-0060独立Approved已写回各自证据/ADR/计划/任务；新发现Low如实
  列出，未顺手混入本原子任务实现。

独立复核请挑战测试是否只验自己、根/子和引擎边界、取消/门禁关闭/重启后的状态、
只读无副作用、HEAD和错误路径，以及observed与验收的边界；不触碰真实服务。

## 独立复审回执

mymacclaude 在 d46f406 上复跑三个文件 123 passed；32处后端突变，31处被测试
杀死，唯一存活的是给HEAD注入正文：TestClient/httpx会丢弃HEAD正文，原断言
无法检测应用层发送。这是测试能力边界，以上措辞已修正，未声称补了原始ASGI测试。
另指出 sample 在动态文档中错误声明JSON空Schema、resources详情空Schema漏登记；
已明确加入 READ-SCHEMA-01，由HA-0062跟进。全量632未由复审者重跑；非DB
GET副作用、真实发布也不在本次Approved范围。
