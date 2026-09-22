#!/bin/sh
set -eu
cd "$(dirname "$0")/.."
.venv/bin/python -m pytest -q
.venv/bin/python harness/memory_context_evaluation.py
.venv/bin/python harness/memory_graph_evaluation.py
.venv/bin/python harness/memory_entity_catalog_evaluation.py
.venv/bin/python harness/memory_temporal_read_evaluation.py
.venv/bin/python harness/verify_semantic_retrieval_admission.py
node --check frontend/app.js
node --check frontend/research.js
node --check frontend/research-agents.js
node --check frontend/baidu-netdisk.js
node --check frontend/agent-lab.js
node --check frontend/agent-runtime.js
git diff --check
