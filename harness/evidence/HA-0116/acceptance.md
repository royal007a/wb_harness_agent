# HA-0116：132 客服与 DSH 独立发布回执

2026-10-07，用户明确要求刚验收的 DSH 课程版与132现有客服版均部署。两条分支没有合并。本回执是执行者验收，不冒称已获独立复审。

## 入口与固定版本

| 服务 | 入口 | 版本 | 服务/数据 |
|---|---|---|---|
| 客服 | https://118.196.123.132/harness/support | 561a6056ce180ea11c73b3f6ffde0615bb4eb539 | harnessagent，127.0.0.1:8765，/var/lib/harnessagent/harness.db |
| DSH | https://dsh.118.196.123.132.nip.io/dsh | da43bff8caf66ca528c85e81d81b28869c1cb9a4 | harnessagent-dsh，127.0.0.1:8876，/var/lib/harnessagent-dsh/harness.db |

客服561a605与已验收7eaf317的backend/frontend/requirements及发布脚本差异为空，使用既有依赖环境和加密凭证。DSH是准确的已验收da43bff完整Git快照，Linux按package-lock安装官方SDK；没有合入HA93及之后候选。新的systemd/nginx文件独立管理，未修改运行代码。

本机8765客服7eaf317和8876 DSH da43bff先做健康/版本读取，见local-before.json。本次用户指定132，未替换本机服务。远端DSH使用独立非root服务用户、只读源码、专有数据根；这不构成对模型OS沙箱能力的新增声称。

## 备份、发布和验收

- 客服发布前从运行PID解析实际HARNESS_DB；SQLite备份完整性ok：/var/backups/harnessagent/ha0090-20261007T083149Z/harness.db，SHA-256 b82b3dc8fc5803996f4094751c40e7f094df1cb7d3276e4be259807c234b84a6。同目录application.tar.gz与support.conf保留旧应用/override；新release压缩包也保留。旧.venv、.local、data、node_modules等由promoter明确排除保留。
- 独立staging的pip check和app导入通过。客服运行PID3372199；1个Provider、5个会话、知识库、工作流、MCP配置均保留。所有业务表逐行摘要一致；Provider配置及凭证密文一致。health/next_probe_at和探针计数变化来自原有自动探针（总计96→97），不能写成整个服务器零真实Provider请求。本次验收没有主动调用客服模型。
- DSH staging的pip check、SDK import及合成完整运行通过。live由/opt/harnessagent-dsh链接到/opt/harnessagent-releases/dsh-da43bff8caf6；首次以非root启动时Git safe.directory写成符号链接路径，导致启动被拒绝；改为实际目录后恢复，未放宽到全局通配。此前没有发布公网DSH入口，客服持续正常。新服务已enable，未做整机重启验证。
- DSH live创建run_9913f38cd30c4429b7361a45fdb84493；公网浏览器创建run_9b3b60c7282a450aa12c5e0676724707。两者均succeeded、3次合成Provider协议调用、520合成Token、reserved=0、55事件，付款期限及例外有证据、business_status=partial。JSON和文本产物均核对字节数/SHA-256；合成模式不证明真实模型语义准确率。
- DSH PID3376835重启为3380110后，上述两个Run、账本和产物再次核对成功；未新建替代Run。重启前备份/var/backups/harnessagent/ha0116-dsh-20261007T083810Z/harness.db，SHA-256 171f530460b9c6eadafbbad72e0d06006829578f677213063e400be8eed85f8d，完整性ok。备份可读取，但未做恢复演练。
- nginx语法检查通过；已有workbench配置有duplicate MIME type警告，本次没有修改该配置。两个入口未认证401、临时Basic认证后200，静态JS/CSS均200；DSH的HTTP跳转HTTPS，外部Skill包路径403。桌面页面无JS错误，DSH手机无横向溢出。第一次截图恰逢历史列表异步刷新；browser-after-restart截图已等待列表和详情均显示已完成。
- 临时Basic账户以SSH stdin传递内存生成的哈希、finally删除；最终检查无残留。未复制本机Keychain、数据库或业务记录到远端。DSH数据库仅含本次两个公开合成Run。

## 已知限制

- DSH远端真实豆包Provider未启用、未配置credential_ref；目前只开放合成Provider联调。不能把本机真实模型验收宣称为服务器真实模型验收。客服已有真实Provider与自动探针保持启用。
- 沿用132现有自签HTTPS证书和Basic账户，浏览器可能提示证书不受信任；验收客户端显式忽略证书校验，不声称公开CA验证通过。
- 服务器磁盘发布后仅余约1.20GB（约1.12GiB）。已清掉本任务用完的客服staging和传输临时包，旧发布/备份未擅自清理；后续扩容或整理需另列任务。
- 应用页脚“独立本地实例/与原8765、132隔离”沿用固定源码的本机措辞；实际远端拓扑以上述服务、数据库和入口为准。
- 本次未重跑第七轮完整门禁；其1852 passed/22 skipped及非独占限制沿用原批准快照。仅新增发布、Linux依赖、合成行为、HTTP/UI与重启持久化验收。

## 复核入口

local-before.json、support-deployment.json、ha0116-support-preservation.json、ha0116-support-content-preserved.json、ha0116-dsh-preflight.json、ha0116-dsh-live.json、ha0116-dsh-restart.json、ha0116-dsh-persistence.json、ha0116-final.json；browser/result.json与browser-after-restart/result.json及PNG。部署模板在deploy/harnessagent-dsh.service与deploy/nginx-dsh-course.conf；验证脚本为verify_dsh_release.py及verify_dual_proxy_release.py。

回退DSH仅需禁用新服务、移走新vhost并nginx -t/reload，保留DSH数据库与release；不会触及客服。客服按上述备份恢复应用及override，数据备份恢复需要另行明确判断，不能在运行中直接覆盖数据库。
