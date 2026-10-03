# ADR-0063：损坏的Team记录不是权限撤销

状态：代码与回归完成，待固定提交独立review及双部署。基线7ac1498，HA-0063。

读路径曾以status != active判断归档/撤销，导致未知值和合法inactive混淆；
Channel的SQL workspace_id与JSON workspace_id不一致时还能在错误目录展示。

决定：读取五类Foundation行时使用现有Schema检查结构/类型/枚举，并绑定SQL键；
损坏返回固定500/TEAM_STATE_CORRUPT，不修数据。权限逻辑仅处理已验证记录。
Channel列表复用HA-0060的(code,status)白名单。身份目录保留合法inactive展示。

不新增登录/模型/自动修复。格式注解、全库孤立引用扫描与其他模块数据结构不在
本次完整性检查范围。验收见specs/testing/TEAM_STATE_INTEGRITY.md。
