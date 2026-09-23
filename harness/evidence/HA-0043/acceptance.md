# HA-0043 验收证据

- 资料：课程 PDF 17–22，共 50 页；文件指纹见 `harness/evidence/course-17-22-manifest.json`，阅读总结见 `docs/research/PI_CONTRACT_COURSE_17_22.md`。
- 契约：`specs/v1/pi-contract-pipeline.schema.json`；接口：`POST /api/local/pi-contract-pipeline/preview`。
- 定向测试：3 passed。
- 全量验证：`sh harness/verify.sh` → **273 passed, 12 skipped, 1 warning**。
- 本地：launchd 重启后 `http://127.0.0.1:8765/api/v1/health` 返回 `status=ok`；Pi admission 为 `not_admitted`，model/external calls 均为 0。
- 远端：从 systemd 解析到 `HARNESS_DB=/var/lib/harnessagent/harness.db`，先创建了带时间戳的数据库备份，再 staging 预检、安装锁定依赖、promotion 和重启；loopback health 为 `ok`，Pi admission 仍为 `not_admitted`。
- 公网入口：现有 nginx HTTP 会 301 到 HTTPS；HTTPS 未带认证返回 401。没有改动认证、TLS 或服务边界。
- 远端部署细节（不含凭据）见 `deployment.json`。
