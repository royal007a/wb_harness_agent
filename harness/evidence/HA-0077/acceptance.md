# HA-0077 证据（持续补充）

用户要求两小时内建 DSH 分支，实现、本地部署、给 URL 并请 mymacclaude review。基线87968aa，工作目录和服务不与原8765/132共用。

## 已执行

- npm固定版本安装成功，官方SDK实际握手成功；不是自写循环冒名DSH。
- 最初6项真实DSH子进程测试通过；扩展后22项通过，覆盖工具循环、预算预拒绝、等待Provider时取消、失败不重试、输入/同源/默认禁用、幂等/重启、环境秘密和NODE_OPTIONS隔离、坏usage/截断/bash/未读证据不发布。
- 首次相关测试162 passed（6 DSH + workbench/runtime_event_metadata/business_budget）；最终定向XML另列。
- 真实模型合成合同探针：run_34b75d5d2b654b1088624650579113aa，succeeded；固定doubao-seed-2.1-lite、用户指定coding/v3；4次模型、5次工具，usage累计3683，预留归零，1个产物。临时库已由TemporaryDirectory清理；这是实时工具执行记录，不是保留库快照。后续部署探针另存持久证据。
- 凭证只从用户指定历史消息导入Keychain，未回显；进程原有ARK_API_KEY不是Coding Key，未使用。

## 本地部署与独立复审

- 代码固定 d813b63，mymacclaude 复审 Approved；独立28项及原样SIGKILL探针通过。范围仅代码/离线反例，不冒充对方核验了真实 Provider。
- 8876在当前已授权登录会话中使用 `local.harnessagent.dsh-session`，launchd PID与唯一监听PID一致（deployment.json）。原main仍为87968aa且干净，未改8765/132。
- 浏览器实际运行（Chromium151.0.7922.34）：合成Run `run_4e86c90c721a44a08bcf84c49e1191ef`，2次模型接口、430合成Token；真实Run `run_ce561e298d534404bf05ba45014b4c69`，doubao-seed-2.1-lite，2次请求、1次工具、1795实报Token，预留0、1个产物。真实模式没有脚本fallback。
- 桌面1440×1050、移动390×844：创建/轮询终态/引用clause-1/付款30天/历史回读/下载/无横向溢出/无JS错误均通过（browser.json、dsh-desktop/mobile.png）。默认合成的断言独立存在；桌面图是真实模式显式选择后的结果。
- 原工作台在此独立8876实例的浏览器回归通过（workbench/browser.json）；没有打开或修改原8765实例。
- 产物下载的SHA和大小与持久登记匹配；DSH临时工作目录残留0。资源与最终产物按产品设计留在DB，不把临时会话清理称为删除所有产品数据。
- 返工后全量1552 passed /22 skipped（full-final.xml/log）。之后仅调整测试断言顺序并新增超时/空检索两个用例，定向30 DSH +57 workbench =87 passed（review-fixes.xml）。最后重新执行统一verify（verify-final.log，exit0）：1554 passed /22 skipped，包含全部最新测试与评测、155个方法/路径清单、三个DSH JavaScript文件语法检查。
- 最终DSH测试文件SHA256：01af51762764a35c44f2f55bf2407537cde6258096ef07dfad1739241ee98af4。生产代码相对复审d813b63无变动；后续提交只含测试、文档、验证脚本与证据。最后重启后的身份和历史产物回读回执输出 `.local/dsh-deployment-final.json`；已提交的deployment.json记录的是此前d813b63这次实际部署，不篡改其时间和版本。
- 4个反例放回c1cdf4f：4 failed /24 deselected /0 errors（before-review-fixes.xml/log）：SIGKILL在残留目录断言失败，而非缺字段/导入；未授权请求确实使Run失败；缺引用/未读引用原本会发布。测试放在额外文件test_dsh_revision.py，模块名变化不改变断言。

## 已知保守边界

- 恢复等待5秒后仍活着的进程组对应目录保留pending；本切片没有后台清理重试，要下次重启再次检查。未登记/符号链接/身份变化也不自动删。
- 当前登录会话退出或机器重启后的自动恢复未验收；README所列启动命令需在有Keychain授权的会话执行。不是无条件开机自启。
- 新HTTP响应完整静态/动态OpenAPI绑定未补齐；Input、Adapter结果和核心Task/Run/Event/Artifact契约已有校验，不称全量API契约完成。

## 首轮 review 返工与部署诊断

- 5a72202 收到 Changes Requested：SIGKILL 后 SDK 正文残留；未授权网关请求导致 Run 失败；UI 默认真实模式。
- 返工增加平台自有目录登记（设备/inode、进程组、租约）、恢复前检查进程组已退出、只删登记路径。真实 SIGKILL 测试先确认合成秘密已落入 SDK jsonl，再杀服务、恢复；文件残留为零。活进程、未登记目录、符号链接和被替换目录保留不误删。
- 网关未认证403不污染当前Run；页面默认合成；额外拒绝空证据与未读引用。DSH新增28项，连同workbench共85 passed（review-fixes.xml）。
- 5a72202阶段全量1546 passed / 22 skipped（full.xml/log）；其中worktree无pi-adapter node_modules多6项跳过。这不是返工后全量结果。
- 原8876 user/501部署两次真实调用均为 MODEL_CREDENTIAL_UNAVAILABLE，没有假称模型成功。相同引用在当前调用会话的命令行成功；安全诊断发现 user/501 Keychain OSStatus=-25308（禁止交互），显式 security CLI 也返回36；没有改Keychain ACL或复制明文密钥。KEYCHAIN_PATH被keyring忽略，已移除。
- 后续部署使用当前已授权会话的独立 launchctl submit job；会话/重启边界另见运行文档，实际验收待补。

## not_evidence

不是132部署；不是OS沙箱、恶意上游包隔离、完整检索质量评测、真实私密合同审查、投资建议验收。模型符合官方上下文/输出上限是保守预留的前提，取消不保证Provider不再计费。输出为待人工复核草稿。
