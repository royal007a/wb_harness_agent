#!/bin/sh
set -eu
cd "$(dirname "$0")/.."
.venv/bin/python -m pytest -q
node --check frontend/app.js
node --check frontend/research.js
git diff --check
