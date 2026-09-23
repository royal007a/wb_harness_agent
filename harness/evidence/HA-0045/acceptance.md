# HA-0045 验收证据

- 组件：`backend/pi_security_guard.py`
- 契约：`specs/v1/pi-security-guard.schema.json`
- 接口：`POST /api/local/pi-contract-pipeline/security-check`
- 行为：metadata-only；`model_calls=0`、`external_calls=0`；未知能力和越权输入 fail-closed。
- 定向测试：`tests/test_pi_security_guard.py`（3 tests）
- 全量：278 passed, 12 skipped, 1 warning。
- 本机：`http://127.0.0.1:8765/api/v1/health` 为 ok；security-check 未知工具返回 deny，model/external calls 均为 0。
- 公网机：`118.196.123.132` systemd 服务重启后 loopback health 为 ok；同一 security-check 冒烟返回 deny，数据目录数据库已先备份。
- 发布提交：`13cb52a`。
