# HA-0118 交付与复审记录

用户要求完善部署验证spec/测试skill，安装Codex和Claude，并交由mymacclaude复审。本次只改技能、离线校验器、spec和治理记录，没有部署或重启业务，没有读取密钥或调用Provider。

新增skills/harnessagent-deployment-verification：SKILL.md、项目映射、证据合同、只读JSON/摘要校验器和21个离线测试。specs/testing/DEPLOYMENT_VERIFICATION.md将运行版本、真实DB备份、入口验收、诊断绕行和最终状态分离。既有local-agent-lab-delivery保持其ADR-0021专用范围。

已运行：标准库unittest 21通过（tests.txt），skill-creator quick_validate通过（skill-structure.txt），git diff --check通过。测试包含多个传输/类型子例，但只报unittest的21项，不把子例累加成虚高覆盖率。所有观测为临时目录中的合成声明，不是实际部署证据。

校验器只证明输入声明与文件绑定一致；不联网，不独立证实日志真实性/计划完备/公网可达/数据恢复。固定plan摘要不能阻止作者重新编造一份新plan，故plan必须先经spec/需求对账，不能以机械通过替代review。安装与独立review回执随后补齐；当前不声称review通过。

安装前检查发现两个用户目录中出现了llm-quant-lab用途的deployment-verification（与最初目录盘点不同）。本次没有覆盖它，将技能命名为harnessagent-deployment-verification；通用只读脚本继续可移植，自动发现描述限定HarnessAgent。

## 双端安装及复审请求

9564d4436b91a897e379297e5e252ae815194ee3的skill包已复制到~/.codex/skills/harnessagent-deployment-verification和~/.claude/skills/harnessagent-deployment-verification。6个文件逐一SHA匹配，各安装从/tmp独立运行同一套21测试均通过，不将重复运行计成63项覆盖。installation.json记录精确路径、文件摘要和未做会话热加载测试。

dc03d9202bc46a5575b9347645e999a4c4410853（代码与9564d44相同，增加安装回执）已通过飞书om_x100b63502bb404a8b1756650e6fa077交给用户指定的mymacclaude只读复审。范围包括规范、独立反例、安装一致性及一例skill引导判定；禁止业务系统/凭证访问及共享目录写入。当前等待实际回复，未声称Approved。

## dc03d92 review修订（2026-10-08）

独立review：飞书om_x100b634536d944a8b29f69b6905efd3，Changes Requested，2 Medium与5 Low。该结论未被作者自测替代，当前仍待修订版复核。

- M1：公网计划必须声明整数2xx的http_status与application_ok=true；仅URL/transport/TLS的计划直接invalid。401/502观察值及200但应用失败均failed；修改期望为失败状态也invalid。合同示例同步。
- M2：public_entry=null时禁止同名检查；诊断另名登记。输出public_entry_required明确是否包含公网验收。
- L1：identity.expected必须含严格布尔identity_stable=true，缺失/false/1均invalid。health仍按计划中的具体健康断言核对，不以统一状态名代替不同服务语义。
- L2：输出plan_sha256；spec要求发布前登记，CLI新增--expected-plan-sha256，可拒绝事后同时重写plan/receipt。登记时间/身份仍需独立证据，不由校验器证明。
- L3：SKILL与合同强制最终报告逐目标列prior_failed_attempts（包括0），关联原失败原因/证据。最后成功仍可verified，重试本身不自动变成例外，历史失败不可隐去。
- L4：RecursionError按invalid/exit2返回，无traceback。
- L5：项目映射明确132两个公布入口必须HTTPS，HTTP仅可另列重定向检查。

测试：在未改校验器时，用新增回归运行32项出现预期失败（review-regression-before.txt；含subTest失败，不将失败数视为独立用例数）；修订后同32项全部通过（review-regression-after.txt），其中原21项全部保留。quick_validate、git diff --check通过。测试仅临时目录合成声明，无业务服务或Provider访问。双端更新安装回执随后记录。

修订安装：22c26b1的6个文件在确认旧安装未漂移后同步到两端，更新前副本已备份（installation.json记录位置，installation-initial.json保留首版清单）。两端各自从/tmp跑相同32项测试通过，逐文件SHA与源包一致；会话热加载未测试，不累加为96项覆盖。

## 最终状态：completed（2026-10-08）

mymacclaude已对aa7d0f9给出Approved，原2 Medium与5 Low闭合；原始回执、范围和旧plan迁移提示见independent-review.md。批准仅离线校验器/文档/双端安装，不扩展到公网或部署。此前“等待复审”的记录保留为历史。
