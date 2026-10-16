#!/usr/bin/env bash
# MVP check (W4-7): start the spec-bridge API on 127.0.0.1:8000, upload one document,
# save the registration JSON, print a summary and stop the server.
#
#   scripts/mvp_check.sh openai  [document]   # cloud LLM: pipeline wiring check (fast)
#   scripts/mvp_check.sh ollama  [document]   # local LLM: the local-first MVP check
#
# Default document: data/synth/inputs/SYN-004.docx (has a duplicate in the dev registry).
# Port 8000 must be free; if another program holds it, the script stops and names it
# instead of killing anything.
set -euo pipefail

PROVIDER="${1:-openai}"
DOCUMENT="${2:-data/synth/inputs/SYN-004.docx}"
PORT=8000
URL="http://127.0.0.1:${PORT}"
NAME="$(basename "${DOCUMENT%.*}")"
OUT="var/api/${NAME}-${PROVIDER}.json"
LOG="var/api/server-${PROVIDER}.log"

cd "$(dirname "$0")/.."
mkdir -p var/api

if [[ "$PROVIDER" != "openai" && "$PROVIDER" != "ollama" ]]; then
  echo "usage: scripts/mvp_check.sh openai|ollama [document]" >&2
  exit 2
fi
if [[ ! -f "$DOCUMENT" ]]; then
  echo "document not found: $DOCUMENT" >&2
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
  SPEC_BRIDGE_PROVIDER=openai uv run uvicorn spec_bridge.api.app:app \
    --host 127.0.0.1 --port "$PORT" >"$LOG" 2>&1 &
else
  OFFLINE=1 SPEC_BRIDGE_PROVIDER=ollama uv run uvicorn spec_bridge.api.app:app \
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

# 4) Upload and time it.
START=$(date +%s)
HTTP=$(curl -s -o "$OUT" -w '%{http_code}' -F "file=@${DOCUMENT}" "${URL}/documents")
END=$(date +%s)
echo "upload: HTTP ${HTTP}, $((END - START)) s (includes building the service on first request)"
echo "saved: $OUT"

# 5) Summary.
python3 - "$OUT" <<'PY'
import json, sys
r = json.load(open(sys.argv[1]))
if "status" not in r:
    print(json.dumps(r, indent=2)[:1500]); sys.exit(1)
v = r["validation"]
print(f"class      : {r['class_id']}  (candidates {r['class_candidates']})")
print(f"status     : {r['status']}   failure: {r['failure']}")
print(f"facts      : {len(r['facts'])}   unresolved: {len(r['unresolved'])}")
print(f"findings   : {[(f['code'], f['attribute_ids']) for f in v['findings']]}")
print(f"missing    : {v['missing_required']}")
print(f"matches    : {[(m['registry_id'], m['relation']) for m in r['matches'] if m['relation'] == 'duplicate']} duplicate, "
      f"{sum(m['relation'] == 'similar' for m in r['matches'])} similar")
print(f"model      : {r['provenance'].get('model', {}).get('name')}")
PY
