#!/usr/bin/env bash
# Start or stop an isolated local demo. Existing storage/ is never touched.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
RUNTIME="$ROOT/.demo-runtime"
BACKEND_PORT="${RFQ_DEMO_BACKEND_PORT:-8010}"
FRONTEND_PORT="${RFQ_DEMO_FRONTEND_PORT:-3010}"

port_in_use() {
  lsof -nP -iTCP:"$1" -sTCP:LISTEN -t 2>/dev/null | grep -q .
}

stop_owned() {
  local name pid_file pid command cwd expected_cwd
  for name in frontend backend; do
    pid_file="$RUNTIME/$name.pid"
    [[ -f "$pid_file" ]] || continue
    pid="$(cat "$pid_file")"
    command="$(ps -p "$pid" -o command= 2>/dev/null || true)"
    cwd="$(lsof -a -p "$pid" -d cwd -Fn 2>/dev/null | sed -n 's/^n//p' | head -n 1)"
    expected_cwd="$ROOT"
    [[ "$name" == frontend ]] && expected_cwd="$ROOT/frontend"
    if [[ -n "$command" && "$cwd" == "$expected_cwd" ]]; then
      if { [[ "$name" == backend && "$command" == *"uvicorn rfq_assistant.api.app:app"* ]]; } || \
         { [[ "$name" == frontend && "$command" == *"next/dist/bin/next dev"* ]]; }; then
        kill "$pid" 2>/dev/null || true
        echo "Stopped demo $name (PID $pid)."
      else
        echo "Leaving PID $pid alone; it no longer matches the recorded demo $name command."
      fi
    fi
    rm -f "$pid_file"
  done
}

case "${1:-start}" in
  stop)
    stop_owned
    exit 0
    ;;
  start) ;;
  *) echo "Usage: $0 [start|stop]" >&2; exit 2 ;;
esac

stop_owned
if port_in_use "$BACKEND_PORT"; then
  echo "Backend port $BACKEND_PORT is already in use. Set RFQ_DEMO_BACKEND_PORT to a free port." >&2
  exit 1
fi
if port_in_use "$FRONTEND_PORT"; then
  echo "Frontend port $FRONTEND_PORT is already in use. Set RFQ_DEMO_FRONTEND_PORT to a free port." >&2
  exit 1
fi

rm -rf "$RUNTIME"
mkdir -p "$RUNTIME/storage" "$RUNTIME/logs"
PYTHON="$ROOT/.venv/bin/python"
[[ -x "$PYTHON" ]] || PYTHON="$(command -v python3)"
NODE="$(command -v node || true)"
if [[ -z "$NODE" || ! -d "$ROOT/frontend/node_modules/next" ]]; then
  echo "Node.js and frontend dependencies are required. Run npm install in frontend/ first." >&2
  exit 1
fi

cd "$ROOT"
RFQ_ASSISTANT_STORAGE_DIR="$RUNTIME/storage" \
RFQ_ASSISTANT_DB_PATH="$RUNTIME/storage/rfq_assistant.sqlite3" \
RFQ_ASYNC_INGEST_ENABLED=false \
  "$PYTHON" -m uvicorn rfq_assistant.api.app:app --host 127.0.0.1 --port "$BACKEND_PORT" \
    > "$RUNTIME/logs/backend.log" 2>&1 &
echo $! > "$RUNTIME/backend.pid"

cd "$ROOT/frontend"
RFQ_ASSISTANT_API_URL="http://127.0.0.1:$BACKEND_PORT" \
RFQ_E2E_NEXT_DIST_DIR=".next-demo" \
  "$NODE" ./node_modules/next/dist/bin/next dev --webpack --hostname 127.0.0.1 --port "$FRONTEND_PORT" \
    > "$RUNTIME/logs/frontend.log" 2>&1 &
echo $! > "$RUNTIME/frontend.pid"
cd "$ROOT"

cleanup_on_exit() {
  stop_owned
}
trap cleanup_on_exit EXIT INT TERM

wait_for_url() {
  local url="$1" label="$2" attempt
  for attempt in $(seq 1 60); do
    if curl --silent --fail "$url" >/dev/null; then return 0; fi
    sleep 1
  done
  echo "$label did not become ready. See $RUNTIME/logs/" >&2
  stop_owned
  exit 1
}
wait_for_url "http://127.0.0.1:$BACKEND_PORT/api/health" backend
wait_for_url "http://127.0.0.1:$FRONTEND_PORT/workspace" frontend

cat <<INFO
Demo is ready:
  Workspace: http://localhost:$FRONTEND_PORT/workspace
  Backend:   http://127.0.0.1:$BACKEND_PORT/api/health
  Fixtures:  $ROOT/fixtures/rfq_samples/
  Logs:      $RUNTIME/logs/
  Stop:      $ROOT/scripts/demo.sh stop

This run uses a fresh isolated database under .demo-runtime/ and synchronous ingestion.
The existing storage/ directory is unchanged.
Keep this command running while presenting; press Ctrl+C to stop its servers.
INFO

wait "$(cat "$RUNTIME/frontend.pid")"
