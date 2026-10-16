#!/usr/bin/env bash
# S1/S2 demo through the job API (W5-4): start the spec-bridge API on 127.0.0.1:8000 with
# a fresh app folder, run scripts/s1_s2_api_demo.py against it, stop the server.
#
#   scripts/s1_s2_api_demo.sh openai   # cloud LLM: wiring check (fast)
#   scripts/s1_s2_api_demo.sh ollama   # local LLM: the local-first run
#
# The app folder is var/app-demo/<time>/ (registry, checkpoints, uploads): your var/app is
# not touched. Port 8000 must be free; the script names the holder instead of killing it.
set -euo pipefail

PROVIDER="${1:-openai}"
PORT=8000
URL="http://127.0.0.1:${PORT}"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
APP_DIR="var/app-demo/${STAMP}"
LOG="${APP_DIR}/server.log"

cd "$(dirname "$0")/.."
mkdir -p "$APP_DIR"

if [[ "$PROVIDER" != "openai" && "$PROVIDER" != "ollama" ]]; then
  echo "usage: scripts/s1_s2_api_demo.sh openai|ollama" >&2
  exit 2
fi

# 1) Who holds the port?
HOLDER="$(lsof -nP -iTCP:${PORT} -sTCP:LISTEN -t 2>/dev/null || true)"
if [[ -n "$HOLDER" ]]; then
  echo "port ${PORT} is in use by:"
  for pid in $HOLDER; do ps -p "$pid" -o pid=,command=; done
  echo
  echo "Stop that program first (Ctrl+C in its terminal, or: kill <pid>), then run again."
  echo "The script does not stop it for you: it may belong to another project."
  exit 1
fi

# 2) Start the server in the background (cloud: no OFFLINE; local: OFFLINE=1).
if [[ "$PROVIDER" == "openai" ]]; then
  SPEC_BRIDGE_APP_DIR="$APP_DIR" SPEC_BRIDGE_PROVIDER=openai uv run uvicorn spec_bridge.api.app:app \
    --host 127.0.0.1 --port "$PORT" >"$LOG" 2>&1 &
else
  OFFLINE=1 SPEC_BRIDGE_APP_DIR="$APP_DIR" SPEC_BRIDGE_PROVIDER=ollama uv run uvicorn spec_bridge.api.app:app \
    --host 127.0.0.1 --port "$PORT" >"$LOG" 2>&1 &
fi
SERVER=$!
trap 'kill "$SERVER" 2>/dev/null || true' EXIT

# 3) Wait until /health answers (and make sure it is spec-bridge, not another app).
for _ in $(seq 1 60); do
  if curl -s "${URL}/health" | grep -q '"ok"'; then break; fi
  if ! kill -0 "$SERVER" 2>/dev/null; then
    echo "server exited; last lines of $LOG:" >&2
    tail -20 "$LOG" >&2
    exit 1
  fi
  sleep 1
done
TITLE="$(curl -s "${URL}/openapi.json" | python3 -c 'import sys,json; print(json.load(sys.stdin)["info"]["title"])')"
if [[ "$TITLE" != "spec-bridge" ]]; then
  echo "the server on ${PORT} is '$TITLE', not spec-bridge" >&2
  exit 1
fi
echo "server ready ($PROVIDER) on ${URL}"

# 4) The demo (S1, S2a, S2b) and where everything was kept.
uv run python scripts/s1_s2_api_demo.py "$URL" 2>&1 | tee "${APP_DIR}/demo.txt"
echo
echo "kept in ${APP_DIR}/: registry.sqlite (products, edits, audit), checkpoints.sqlite, uploads/, demo.txt"
