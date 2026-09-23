# HA-0044 验收证据

- Skill validator：`quick_validate.py skills/contract-risk-review` → valid。
- 定向测试：pipeline preview/review + Skill script → 5 passed。
- 全量验证：`sh harness/verify.sh` → **275 passed, 12 skipped, 1 warning**。
- 本地 launchd：`/api/v1/health` 为 `ok`，OpenAPI 含 `/api/local/pi-contract-pipeline/review`。
- 公网 systemd：备份 `/var/lib/harnessagent/harness.db` 后 staging 预检、依赖安装、promotion、重启；loopback health 为 `ok`，OpenAPI 含 review 端点。
- review 输出始终 `needs_human`，证据引用绑定当前资源与 chunk SHA256；`model_calls=0`、`external_calls=0`。
- 未启用真实 Provider、联网、法律结论或自动 Gate；不将候选结果描述为正式交付。
