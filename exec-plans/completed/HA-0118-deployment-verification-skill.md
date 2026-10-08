# HA-0118：部署验证skill

用户要求完善部署验证spec/测试skill，安装Codex、Claude，由mymacclaude review。基于HA-0116/117实际边界，新增通用skill，不扩大原Agent Lab零模型SOP范围。

范围与验收见specs/testing/DEPLOYMENT_VERIFICATION.md。顺序：spec/skill与只读验证器→离线反例/skill格式校验→同内容安装两端→固定SHA交给Claude→修订复审问题并核对安装摘要。此次不重启业务、不发模型请求；不以技能维护触发AGENTS的业务双部署。

状态：completed。aa7d0f9（实现22c26b1）获mymacclaude独立Approved，范围限离线校验器、文档及两端安装。32项测试通过，原CR闭合；见harness/evidence/HA-0118/independent-review.md。旧plan迁移须重新登记摘要。未操作业务部署。
