# HA-0077 证据（持续补充）

用户要求两小时内建 DSH 分支，实现、本地部署、给 URL 并请 mymacclaude review。基线87968aa，工作目录和服务不与原8765/132共用。

## 已执行

- npm固定版本安装成功，官方SDK实际握手成功；不是自写循环冒名DSH。
- 最初6项真实DSH子进程测试通过；扩展后22项通过，覆盖工具循环、预算预拒绝、等待Provider时取消、失败不重试、输入/同源/默认禁用、幂等/重启、环境秘密和NODE_OPTIONS隔离、坏usage/截断/bash/未读证据不发布。
- 首次相关测试162 passed（6 DSH + workbench/runtime_event_metadata/business_budget）；最终定向XML另列。
- 真实模型合成合同探针：run_34b75d5d2b654b1088624650579113aa，succeeded；固定doubao-seed-2.1-lite、用户指定coding/v3；4次模型、5次工具，usage累计3683，预留归零，1个产物。临时库已由TemporaryDirectory清理；这是实时工具执行记录，不是保留库快照。后续部署探针另存持久证据。
- 凭证只从用户指定历史消息导入Keychain，未回显；进程原有ARK_API_KEY不是Coding Key，未使用。

## 待补

独立8876部署、桌面/390px浏览器、固定提交review、全量回归。不得在这些完成前称整个任务完成。

## not_evidence

不是132部署；不是OS沙箱、恶意上游包隔离、完整检索质量评测、真实私密合同审查、投资建议验收。模型符合官方上下文/输出上限是保守预留的前提，取消不保证Provider不再计费。输出为待人工复核草稿。
