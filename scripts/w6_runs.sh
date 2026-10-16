#!/usr/bin/env bash
# W6 evaluation runs (D-080), local model, offline, one after another.
#
#   scripts/w6_runs.sh dev           # W6-3: reproduce R, E0, E1SV on the dev split
#   scripts/w6_runs.sh test          # W6-4: R, A, B, C, Copt, E0, E1SV on the test split (once)
#   scripts/w6_runs.sh handwritten   # W6-4: R, E0, E1SV on the handwritten set (once)
#   scripts/w6_runs.sh test Copt     # only the configurations named after the split
#
# C is the W4-1 required-context design (kept as run, D-089); Copt is C with optional
# context, the zero-shot row of the D-053 comparison table and E's extraction step.
#
# test and handwritten refuse to start unless the freeze record matches the system
# (uv run python -m spec_bridge.eval.freeze verify). Logs: var/eval/w6-<split>-<time>.log
set -euo pipefail

SPLIT="${1:-}"
case "$SPLIT" in
  dev) CONFIGS=("R" "E0" "E1SV") ;;
  test) CONFIGS=("R" "A" "B" "C" "Copt" "E0" "E1SV") ;;
  handwritten) CONFIGS=("R" "E0" "E1SV") ;;
  *) echo "usage: scripts/w6_runs.sh dev|test|handwritten [config ...]" >&2; exit 2 ;;
esac
if [[ $# -gt 1 ]]; then CONFIGS=("${@:2}"); fi

cd "$(dirname "$0")/.."
mkdir -p var/eval
LOG="var/eval/w6-${SPLIT}-$(date -u +%Y%m%dT%H%M%SZ).log"

if [[ "$SPLIT" != "dev" ]]; then
  uv run python -m spec_bridge.eval.freeze verify | tee -a "$LOG"
fi

for config in "${CONFIGS[@]}"; do
  case "$config" in
    E0) args=(--config E --rag e0) ;;
    E1SV) args=(--config E --rag e1 --self-check --resolve-conflicts) ;;
    Copt) args=(--config C --context optional) ;;
    *) args=(--config "$config") ;;
  esac
  echo "=== $SPLIT $config $(date -u +%H:%M:%S)" | tee -a "$LOG"
  OFFLINE=1 uv run python -m spec_bridge.eval.experiment "${args[@]}" --split "$SPLIT" 2>&1 \
    | tee -a "$LOG"
done
echo "=== done; log: $LOG" | tee -a "$LOG"
