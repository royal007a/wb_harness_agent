---
name: csv-group-analysis
description: 对已授权 CSV 做单列分组的确定性聚合，生成可溯源结果文件；适用于离线表格分析，不抓取外部数据。
---

# 离线分组分析

此包是项目内能力样例，未自动安装到 Claude/Codex 的用户配置，也未启用任何 SDK 路由。

1. 确认输入资源、分组列、数值列与聚合方式（sum/mean/min/max/count）。目标有歧义时澄清，不猜测财务口径。
2. 使用平台授予的输入和输出路径，在批准的执行环境运行固定脚本，不重新生成聚合代码：

   `python scripts/aggregate.py --input /inputs/data.csv --output /outputs/result.json --group-by region --metric revenue --operation sum`

   脚本路径相对本 Skill 目录。不得据此取得任意宿主路径、网络或凭证权限。
3. 检查退出码与返回的 status。成功时 stdout 仅提供路径、哈希和行数，详细结果保存在文件；需要时按预算读取该结果，不打印原表。
4. 将结果提交平台验收，报告说明输入哈希、指标与缺失值数量。数字是十进制字符串，不隐式更换单位；count 只计非空有效数值。
5. 空表、未知列、重复列名、非数值、超过 50 组、输出已存在均停止，不覆盖旧产物。修正请求后创建新输出。

Skill 说明不是权限或流程状态机。引用、数值独立回算和发布批准由平台负责；该脚本成功不等于整个 Run 成功。
