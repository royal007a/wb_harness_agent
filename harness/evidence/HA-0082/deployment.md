# HA-0082 部署（8876）
- 部署前版本：29e1966（HA-0081）。
- 148dc5b：label PID 78272 == 8876 监听 PID 78272 → `launchctl remove` → `deploy/start_dsh_session.py` → runtime release 148dc5b，`workspace_recovery` 带 `retries`。
- bc9d3f7（超时修复）：label PID 52977 == 监听 PID 52977 → 同流程 → runtime release bc9d3f7。
- 回滚：在 `~/code/ai/harnessagent-dsh` 检出 29e1966 后按同流程重启。未触碰 8765、132、生产库和 Keychain ACL。
