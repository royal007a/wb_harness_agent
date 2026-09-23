# HA-0047 验收证据

- 组件：`harness/pi_contract_tui.py`
- 输入：metadata-only JSONL `preview`/`finding`/`done` 事件。
- 输出：终端摘要，不包含合同正文；model/external calls 不产生。
- 定向测试：`tests/test_pi_contract_tui.py`。
