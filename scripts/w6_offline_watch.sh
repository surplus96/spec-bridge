#!/usr/bin/env bash
# W6-6 (NFR-01): record every open TCP connection on this machine once a second while a
# local OFFLINE=1 demo runs, so the helper can check that the app and its model server
# talked only to loopback. Stop with Ctrl+C.
#
#   scripts/w6_offline_watch.sh            # writes var/w6-6/connections-<time>.log
#
# Every sample is "=== <UTC time>" followed by `lsof -nP -iTCP` rows (all processes, no
# name lookups). The browser's own traffic shows up too; the check reads the rows of the
# app (python/uvicorn) and the model server (ollama) only.
set -euo pipefail

cd "$(dirname "$0")/.."
mkdir -p var/w6-6
LOG="var/w6-6/connections-$(date -u +%Y%m%dT%H%M%SZ).log"
echo "recording to $LOG (Ctrl+C to stop)"
trap 'echo; echo "saved $LOG"; exit 0' INT
while true; do
  {
    echo "=== $(date -u +%Y-%m-%dT%H:%M:%SZ)"
    lsof -nP -iTCP 2>/dev/null || true
  } >>"$LOG"
  sleep 1
done
