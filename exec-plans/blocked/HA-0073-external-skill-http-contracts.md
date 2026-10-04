# HA-0073 外部Skill HTTP合同与损坏包验证

基线5241fe4。先规格/ADR，再行为反例，再最小修复。

- 补runtime、package、list和audit源合同及静态/动态绑定；核对当前错误和参数。
- 临时ZIP/SQLite、合成Sandbox验证门禁、回放、计数、漂移、原子DB故障及边界。
- 对坏ZIP/manifest只修确定的输入错误，不增加调用权限或吞意外故障。
- 固定基线与定向突变，相关/全量/verify，固定提交交mymacclaude只读审查。
- 不触碰正式DB、Provider、8765/132；部署等待兼容本机拓扑，顺序不变。

实现及离线验证完成：最终50项、相关190 passed/5 skipped；同文件回5241fe4
50项均断言失败，12个定向突变被抓住；最终verify退出0，全量1420/16。
早期测试脚手架与过窄断言已修正、旧日志保留并标注。待固定提交独立review和
兼容本机拓扑后的双部署，不能将本项称为真实容器或Product Run验收。

独立复审d2e0538为Changes Requested：bit11非法UTF-8文件名在ZIP构造时抛错，
尚未转422。返工先补两种名称及合法非ASCII名称的反例，再窄捕获UnicodeDecodeError，
锁定其他程序错误仍500；定向/相关/全量验证后重新提交，部署边界不变。
返工验证：60项定向包含在200 passed/5 skipped相关回归中；verify退出0，
全量1430 passed/16 skipped。待新固定提交独立复审与既定双部署。
