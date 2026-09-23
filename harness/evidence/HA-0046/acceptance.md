# HA-0046 验收证据

- 接口：`POST /api/local/pi-contract-pipeline/review-stream`
- 事件：`preview` → `finding` → `done`。
- 边界：不返回合同原文；确定性流水线，model/external calls 为 0。
- 定向测试：`tests/test_pi_contract_pipeline.py::test_pipeline_review_stream_emits_preview_finding_and_done_without_raw_text`。
