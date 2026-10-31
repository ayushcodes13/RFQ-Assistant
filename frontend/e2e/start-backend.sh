#!/usr/bin/env bash
# Start the FastAPI backend for Playwright. Prefer the repo virtualenv when
# present; CI installs the package into the job's Python instead.
set -euo pipefail

cd "$(dirname "$0")/../.."

mkdir -p "${RFQ_ASSISTANT_STORAGE_DIR:-storage}"

if [[ -x .venv/bin/python ]]; then
  PYTHON=.venv/bin/python
else
  PYTHON=python3
fi

exec "$PYTHON" -m uvicorn rfq_assistant.api.app:app \
  --host 127.0.0.1 \
  --port "${RFQ_E2E_BACKEND_PORT:-8000}" \
  --log-level warning
