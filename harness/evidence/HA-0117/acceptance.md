# HA-0117：移除百度网盘侧栏入口并重新部署

用户截图指定的“百度网盘连接”导航已从index.html、agent-lab.html、baidu-netdisk.html移除，两条分支各删除3行。连接数据与API未改动。

- 客服代码：b8e51b75ce3721c79142b11ac40d5dd44861e62b；本机8765和132均运行此版。
- DSH代码：d0f625e3f00c078a459d3a379089a349594d2c8e；本机8876和132均运行此版。
- 两分支分别运行tests/test_frontend_paths.py：各4 passed、1既有弃用warning。git diff --check通过；没有全量测试或新模型调用。
- 本机先备份实际打开的SQLite，发布后6个HTML页面均无目标导航链接。随后远端独立staging导入、依赖和页面预检通过，再备份当前systemd服务的实际HARNESS_DB后发布。
- 客服备份：/var/backups/harnessagent/ha0090-20261007T094820Z。运行目录继续/opt/harnessagent，数据/var/lib/harnessagent/harness.db，依赖和加密凭证保留。
- DSH备份：/var/backups/harnessagent/ha0117-dsh-20261007T094831Z，完整性ok；运行链接切到/opt/harnessagent-releases/dsh-d0f625e3f00c，/etc/systemd/system/harnessagent-dsh.service.d/release.conf将Git safe.directory固定到实际新目录。依赖与旧版完全一致，node_modules链接到旧发布，旧目录须保留；独立数据库不移动。
- 客服配置/密文与业务表保留（探针health/调度可自然更新），DSH原有2个Run保留，既有Run的账本、55个事件及两份产物字节/SHA-256再次验证；没有新建Run来替代旧证据。
- UI：本机6页、客服公网3页、远端DSH经SSH转发2页均无目标导航，未见脚本错误。公网客服截图remote-support.png可见入口已消失；remote-dsh.png是SSH转发实际远端服务的页面。

## 网络验收限制

从本机直接访问DSH域名两次遇到TLS连接重置（浏览器ERR_CONNECTION_CLOSED、curl35）。DNS仍解析到正确IP；服务器本身访问公开域名返回401，服务和nginx健康。本机用HTTPS公网IP加明确DSH Host亦返回401，临时Basic认证后API/历史产物检查通过。故部署与导航移除完成，但不声称该域名从当前客户端网络直接可达；未修改nginx或扩大本次UI变更。临时Basic账户均已删除，SSH验证转发已关闭。

证据：local.json、local-backups.json、support-deployment.json、ha0117-dsh-deployment.json、ha0117-support-content-preserved.json、ha0117-final.json、ui.json和两张PNG。final.json较早采样发生在浏览器临时账户使用期间，因此保留initial=false与结束后true两个状态，不抹去时序。

DSH远端真实Provider未配置的既有边界不变；现有自签证书不变。磁盘余量约0.96GB，已清理本任务用完的客服staging和传输包，未删除旧发布/备份。
