# HA-0054 验证（进行中）

基于 HA-0053 合成探针确认 Runtime 取消与重复执行缺陷。本项规格已登记；
默认真实模型门禁保持关闭。下面按阶段记录结果，不把中间通过当作发布完成。

## 反证与修复

- `before.xml`：未修改实现时，新增生命周期用例 13 failed、2 passed。
  失败分别暴露取消覆写、重复执行、Session 并发、取消清理、等待超时、失败
  重放计数归零、超长错误码及启动恢复缺失；没有真实网络。
- `after.xml`：首版修复后原 15 项 + 既有 Runtime 3 项，18 passed。
- `targeted.xml`：补充启动保留终态、凭证解析过程中取消、稳定的 ASGI 断线
  场景后，Runtime/Lifecycle/Workbench 共 76 passed。
- 实现使用数据库事务领取，不依赖单个 Runtime 实例的内存锁；重复消费者
  没有取消权。所有终态均保留，取消/失败无 assistant 发布。
- `verify.log`：完整 verify exit 0，325 passed、16 skipped；其后确定性
  评测、两类外发准入拒绝检查、JS 语法与 diff 检查通过。
- 双端发布和独立 review 仍待完成。

## 真实沙箱回归的测试预算问题

首次实际容器测试 15 passed、2 failed，保留 `local-sandbox.xml`，不覆盖。
输出超限/输入只读两例先被 2 秒 start+attach+执行超时终止。独立计时探针
复现 2 秒 TIMEOUT，而生产默认 10 秒预算可分别触达 OUTPUT_LIMIT 和
EXECUTION_FAILED；详见 sandbox-deadline-diagnosis.json。
仅更正测试：timeout 专项仍为 2 秒，其他规则专项用现有默认 10 秒且仍要求
精确错误码与容器/输入目录清理。未修改生产沙箱预算或接受任意失败充当通过。
修正后 `local-sandbox-after.xml`：17 passed，真实本机 Colima 容器。
全量 verify 的容器专项按原设计 skip；单独这次 opt-in 运行才是容器证据。

## 首次发布与跨环境修正

本机 b639b8b 已备份后重载，health=ok，模型 gate 仍关闭；桌面/手机浏览器
通过（local-browser/）。132 staging 为 318 passed、22 skipped、1 failed，
未 promotion。差异仅在 GET/HEAD /openapi.json 的 source 字段：本机框架安装
在仓库 .venv，被误当作项目源码；远端框架在独立环境，登记为 framework。
修复清单生成器的源码归属判定，并增加两类安装布局一致性测试；不删除路由、
忽略差异或放过验证。明细 remote-preflight-first.json。

## 双端发布与边界

- 最终应用版本：912faca19bc9561561e889f5ac377e35b7716d90。
- 本机备份 `.local/backups/ha0054-20261003T151756Z`；132 从运行服务解析的
  DB `/var/lib/harnessagent/harness.db`，备份
  `/var/backups/harnessagent/ha0054-20261003T152011Z`，SQLite 完整性检查通过。
- 132 staging：320 passed、22 skipped；运行依赖下 Workbench/前缀 60 passed；
  发布后 Runtime/Lifecycle/真实外部 Skill 37 passed（remote-postdeploy-tests.xml）。
- 两端 health=ok，Agent Runtime disabled，tool_binding_count=0；独立沙箱
  分别 colima / linux-docker、enabled、blockers=[]。镜像未变。
- 本机与远端前缀浏览器脚本通过，无 JS 错误。远端通过已关闭的 loopback SSH
  隧道与本机前缀代理；不是公网 Basic 密码登录验证。公网未认证仍 401，
  带代理前缀的 Skill packages 请求 403。两端探针容器无残留。
- 视觉检查额外发现 UI-RUNTIME-01：错误仅闪现，拉取持久消息后消失，
  detail.exchanges 未渲染；浏览器旧断言未覆盖此情形。已登记 GAPS，
  **不能把本轮浏览器脚本通过称为错误状态 UI 已验收**。后续单独修复。
- nginx -t 通过；同机原有 workbench 配置重复 text/html MIME warning 未改动。
- 已向 mymacclaude 提交 b639b8b / 912faca 复审，尚未收到本项结论。
  整体 12 小时目标继续；这不是全部功能/API 已验收。
