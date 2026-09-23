# HA-0045 验收证据

- 组件：`backend/pi_security_guard.py`
- 契约：`specs/v1/pi-security-guard.schema.json`
- 接口：`POST /api/local/pi-contract-pipeline/security-check`
- 行为：metadata-only；`model_calls=0`、`external_calls=0`；未知能力和越权输入 fail-closed。
- 定向测试：`tests/test_pi_security_guard.py`（3 tests）
- 余下验证：全量 `harness/verify.sh`、本机与公网部署健康检查。
