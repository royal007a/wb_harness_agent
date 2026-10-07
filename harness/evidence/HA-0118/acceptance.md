# HA-0118 首版交付（等待独立review）

用户要求完善部署验证spec/测试skill，安装Codex和Claude，并交由mymacclaude复审。本次只改技能、离线校验器、spec和治理记录，没有部署或重启业务，没有读取密钥或调用Provider。

新增skills/harnessagent-deployment-verification：SKILL.md、项目映射、证据合同、只读JSON/摘要校验器和21个离线测试。specs/testing/DEPLOYMENT_VERIFICATION.md将运行版本、真实DB备份、入口验收、诊断绕行和最终状态分离。既有local-agent-lab-delivery保持其ADR-0021专用范围。

已运行：标准库unittest 21通过（tests.txt），skill-creator quick_validate通过（skill-structure.txt），git diff --check通过。测试包含多个传输/类型子例，但只报unittest的21项，不把子例累加成虚高覆盖率。所有观测为临时目录中的合成声明，不是实际部署证据。

校验器只证明输入声明与文件绑定一致；不联网，不独立证实日志真实性/计划完备/公网可达/数据恢复。固定plan摘要不能阻止作者重新编造一份新plan，故plan必须先经spec/需求对账，不能以机械通过替代review。安装与独立review回执随后补齐；当前不声称review通过。

安装前检查发现两个用户目录中出现了llm-quant-lab用途的deployment-verification（与最初目录盘点不同）。本次没有覆盖它，将技能命名为harnessagent-deployment-verification；通用只读脚本继续可移植，自动发现描述限定HarnessAgent。
